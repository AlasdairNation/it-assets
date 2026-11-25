import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core import mail
from django.conf import settings
from django.utils.timezone import localtime as now

from organisation.models import DepartmentUser
from organisation.utils import ms_graph_client_token, create_freshservice_ticket, update_freshservice_ticket_status, add_freshservice_ticket_note
from organisation.enum_library import FSTicketStatus as Status, FSTicketSource as Source



class Command(BaseCommand):
    help = "Checks department users for any terminated users, identifies which are beyond the designated grace period, then removes their licenses"

    logger = logging.getLogger("organisation")

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-terminated",
            action="store",
            type=int,
            dest="terminated_account_days",
            help=f"(Optional) Number of days grace for terminated users prior to termination processing (default {settings.TERMINATED_ACCOUNT_DAYS} days)",
        )
        parser.add_argument(
            "--send-failure-email",
            action="store_true",
            dest="send_failure_email",
            help=f"(Optional) Sends admins an email if there are any major failures during termination processing",
        )
        parser.add_argument(
            "--ticket-tracking",
            action="store_true",
            dest="ticketing",
            help=f"(Optional) Creates and updates Freshservice tickets for each user to track their offboarding status",
        )

    def handle(self, *args, **options):
        self.logger.info("Initiating termination processing...")

        # Gets the termination grace period in days
        terminated_account_days = options.get("terminated_account_days", settings.TERMINATED_ACCOUNT_DAYS)
        ticketing = options.get("ticketing", False)
        failure_emails = options.get("failure_emails", False)
        token = ms_graph_client_token()

        # Stages all unstaged terminated users (azure disabled and deletion date set)
        self.stage_terminated_staff(terminated_account_days, ticketing, failure_emails, token)

        # Checks if any users are no longer terminated and resets their termination staging status and deletion date
        self.unstage_returning_staff(terminated_account_days, ticketing, failure_emails)

        # Offboards all expired staged user accounts that have an expired grace period
        self.offboard_staged_staff(terminated_account_days,ticketing, failure_emails, token)

        self.logger.info("Termination processing complete.")


    def stage_terminated_staff(self,terminated_account_days: int, ticketing: bool, failure_emails: bool, token: dict) -> None:
        """
        Stages unstaged terminated staff for offboarding and disables their entra accounts.\n
        Also creates a Freshservice offboarding ticket with related information and notifies the user's manager.\n
        """

        # Retrieve terminated staff who aren't already staged
        self.logger.info("Starting staging step...")
        unstaged_terminated_staff = DepartmentUser.objects.filter(offboarding_staged_at__isnull=True,ongoing=False)
        self.logger.info(f"Found {len(unstaged_terminated_staff)} staff that require staging")

        for staff in unstaged_terminated_staff:
            self.logger.info(f"Attempting to stage '{staff.email}'...")
            # Account management
            try:
                staff.offboarding_staged_at = now()
                staff.save()
                staff.disable_entra_account(token=token,logging_context = "OFFBOARDING")
                self.logger.info(f"Successfully staged '{staff.email}': Microsoft account disabled and staging date recorded.")
            except Exception as exc:
                stage = "staging - account management"
                self.report_exception(exc,staff,stage,ticketing,failure_emails)

            # Ticket management
            if ticketing:
                try:
                    # Create offboarding ticket
                    staff.offboarding_ticket_id = self.create_offboarding_ticket(staff,terminated_account_days)
                    self.logger.info(f"Offboarding ticket '{staff.offboarding_ticket_id}' for '{staff.email}' created.")
                except Exception as exc:
                    stage = "staging - ticket management"
                    self.report_exception(exc,staff,stage,ticketing,failure_emails)


    def unstage_returning_staff(self,terminated_account_days: int, ticketing: bool, failure_emails: bool) -> None:
        """
        Retrieves staged users who're now re-employed.\n
        Updates offboarding ticket for each user, notifies the user's manager, and resolves the ticket.
        """

        self.logger.info("Starting unstaging step...")
        # Retrieve staged staff who are no longer terminated
        returning_staged_staff = DepartmentUser.objects.filter(offboarding_staged_at__isnull=False,ongoing=True)
        self.logger.info(f"Found {len(returning_staged_staff)} staff that require unstaging")

        # Unstaged these staff members
        for staff in returning_staged_staff:
            self.logger.info(f"Attempting to unstage '{staff.email}'...")
            # Ticket management
            if ticketing:
                try:
                    # Create ticket if none existed
                    if staff.onboarding_ticket_id is None:
                        self.create_offboarding_ticket(staff,terminated_account_days)

                    # Update ticket with new relevant data
                    self.add_private_note(
                        staff,
                        f"""New termination record:<br>
                        - Ongoing: {str(staff.ongoing)}<br>
                        - Termination date: {str(staff.termination_date)}"""
                    )
                    self.add_public_note(
                        staff,
                        f"""{staff.get_display_name()} is no longer terminated and their account is no longer staged for deletion.<br>
                        This ticket will now be resolved"""
                    )
                    # Close ticket
                    self.close_offboarding_ticket(staff)
                    self.logger.info(f"Offboarding ticket '{staff.offboarding_ticket_id}' for '{staff.email}' updated and closed.")
                except Exception as exc:
                    stage = "unstaging - ticket management"
                    self.report_exception(exc,staff,stage,ticketing,failure_emails)

            # Account management
            staff.offboarding_staged_at = None
            staff.offboarding_ticket_id = None
            staff.azure_exempt_from_deletion = False
            staff.save()
            self.logger.info(f"Successfully unstaged {staff.email}")


    def offboard_staged_staff(self, termination_grace_period: int, ticketing: bool, failure_emails: bool, token: dict) -> None:
        """
        Offboards staged staff that have exceeded the grace period.\n
        Updates and resolves the offboarding ticket, notifying the manager.\n
        Deletes the entra account, then the DepartmentUser record.
        """

        self.logger.info("Starting offboarding step...")
        # Retrieve all expired staged users, except for those marked as exempt from deletion
        grace_expiry_cutoff = now() - timedelta(days=termination_grace_period)
        staged_expired_staff = DepartmentUser.objects.filter(
            ongoing=False,
            azure_exempt_from_deletion=False,
            offboarding_staged_at__lte=grace_expiry_cutoff
        )
        self.logger.info(f"Found {len(staged_expired_staff)} staff that require offboarding")


        for staff in staged_expired_staff:
            self.logger.info(f"Attempting to offboard '{staff.email}'...")
            # Ticket management
            if ticketing:
                try:
                    # Create ticket if it didn't exist
                    if staff.offboarding_ticket_id is None:
                        staff.offboarding_ticket_id = self.create_offboarding_ticket(staff,termination_grace_period)
                        self.add_private_note(staff,"Staged account found without an offboarding ticket, ticket was during offboarding stage.")

                    # Add public facing note to manager notifying them of the deletion cancelation.
                    self.add_public_note(
                        staff,
                        f"""
                        The Microsoft account of user '{staff.get_display_name()}' has now been deleted.<br>
                        This ticket will now be resolved.
                        """
                        )

                    # close ticket
                    self.close_offboarding_ticket(staff)
                    self.logger.info(f"Offboarding ticket '{staff.offboarding_ticket_id}' for '{staff.email}' updated and closed.")
                except Exception as exc:
                    stage = "offboarding - ticket management"
                    self.report_exception(exc,staff,stage,ticketing,failure_emails)

            # Account management
            try:
                email = staff.email
                staff.delete_entra_account(token)
                staff.delete()
                self.logger.info(f"Successfully offboarded '{email}': Microsoft account and DepartmentUser record deleted")
            except Exception as exc:
                stage = "offboarding - account management"
                self.report_exception(exc,staff,stage,ticketing,failure_emails)
    
    def create_offboarding_ticket(self, staff: DepartmentUser, terminated_account_days: int) -> str | None:
        """
        Creates an offboarding ticket in freshservice
        """
        emails = [staff.manager.email] if staff.manager is not None else []
        # Create offboarding ticket, notifying the user's manager by CCing them in the ticket
        return create_freshservice_ticket(
            subject = f"User Offboarding - {staff.email}",
            description = f"""<b>Automated Offboarding Ticket:</b><br>
            The employee '{staff.email}' was terminated on {staff.termination_date} and their Microsoft account is staged for deletion<br>
            Their account was disabled as of {str(staff.offboarding_staged_at)} and will be deleted {terminated_account_days} days afterwards without intervention.<br>
            This ticket will be used to automatically track the progress of this offboarding process.
            """,
            category = "Service Operations",
            sub_category = "77 Onboard a new staff member",
            status = Status.PENDING,
            source = Source.EMPLOYEE_OFFBOARDING,
            cc_emails = emails
        )
    def add_public_note(self, staff: DepartmentUser, body: str):
        """
        Convenience method to add a public note to the user's offboarding ticket, notifying the user's manager if possbile.
        """
        emails = [staff.manager.email] if staff.manager is not None else []
        # Add public facing note to manager notifying them of the deletion cancelation.
        add_freshservice_ticket_note(
            ticket_id=staff.offboarding_ticket_id,
            private=False,
            notify_emails=emails,
            body=body
            )

    def add_private_note(self, staff: DepartmentUser, body: str):
        """
        Convenience method to add a private note to the user's offboarding ticket.
        """
        emails = [staff.manager.email] if staff.manager is not None else []
        # Add public facing note to manager notifying them of the deletion cancelation.
        add_freshservice_ticket_note(
            ticket_id=staff.offboarding_ticket_id,
            body=body
            )

    def close_offboarding_ticket(self,staff: DepartmentUser):
        """
        Convenience method to close the staff's offboarding ticket
        """
        update_freshservice_ticket_status(ticket_id=staff.offboarding_ticket_id, status=Status.CLOSED)


    def report_exception(self, exc: Exception, user: DepartmentUser, stage: str, ticketing: bool, failure_emails: bool):
        """Convenience method to report failures via email and freshservice"""
        self.logger.exception(f"Failure during '{stage}' stage for user '{user.email}'", exc_info=exc)
        exc_message = str(exc)
        if ticketing and user.offboarding_ticket_id is not None:
            try:
                # Report failure in freshservice ticket and update status to reflect failure
                add_freshservice_ticket_note(
                    ticket_id=user.offboarding_ticket_id,
                    body=f"Failure during '{stage}' stage - IT Assets Admins have been notified and provided failure data",
                )
                update_freshservice_ticket_status(
                    ticket_id=user.offboarding_ticket_id,
                    status=Status.WORKFLOW_FAILED
                )
            except Exception as e:
                self.logger.exception(f"failure during Freshservice ticket error reporting.", exc_info = e)
                # Append Freshservice failure to error message
                exc_message += f" Additional failure occured during Freshservice ticket error report: {str(e)}"
        if failure_emails:
            # Send report of failures to admins
            self.send_failure_email(user,stage, message= exc_message)
            self.logger.info(f"Sent admins failure email regarding '{user.email}'")


    def send_failure_email(self, user: DepartmentUser, stage: str, message: str):
        subject = f"OFFBOARDING: {user.email} failed during {stage}"
        message = f"""
Failure during offboarding processing of '{user.email}' at the stage '{stage}'.
Message: {message}

User Details:
 - ongoing: {str(user.ongoing)}
 - termination_date: {str(user.termination_date)}
 - offboarding_staged_at: {str(user.offboarding_staged_at)}
 - azure_exempt_from_deletion:{str(user.azure_exempt_from_deletion)}
 - offboarding_ticket_id: {str(user.offboarding_ticket_id)}
 - term_date_data: {str(user.term_date_data)}
"""
        html_message = f"""
<p>
Failure during offboarding processing of '{user.email}' at the stage '{stage}'.<br>
Message: {message}<br>
</p>
<p>
User Details:<br>
 - ongoing: {str(user.ongoing)}<br>
 - termination_date: {str(user.termination_date)}<br>
 - offboarding_staged_at: {str(user.offboarding_staged_at)}<br>
 - azure_exempt_from_deletion:{str(user.azure_exempt_from_deletion)}<br>
 - offboarding_ticket_id: {str(user.offboarding_ticket_id)}<br>
 - term_date_data: {str(user.term_date_data)}<br>
</p>
"""
        mail.send_mail(
            subject=subject,
            message=message,
            from_email=settings.NOREPLY_EMAIL,
            recipient_list=settings.ADMIN_EMAILS,
            html_message=html_message,
            fail_silently=True,
        )