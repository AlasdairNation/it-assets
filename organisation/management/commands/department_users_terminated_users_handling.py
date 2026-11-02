import logging
import json
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.core import mail
from django.conf import settings

from organisation.models import DepartmentUser
from organisation.utils import ms_graph_remove_user_licenses, ms_graph_client_token


class Command(BaseCommand):
    help = "Checks department users for any terminated users, identifies which are beyond the designated grace period, then removes their licenses"

    logger = logging.getLogger("organisation")

    def add_arguments(self, parser):
        parser.add_argument(
            "-r",
            "--remove-licenses",
            action="store_true",
            dest="remove_licenses",
            help="(Optional) Flag to remove licenses from terminated users who are past the grace period (default behaviour is logging only",
        )
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
            "--send-summary-email",
            action="store_true",
            dest="send_summary_email",
            help=f"(Optional) Sends a summary of the terminated user processing upon completion",
        )

    def handle(self, *args, **options):
        self.logger.info("Started termination processing command")
        # Gets the termination grace period in days
        terminated_account_days = options.get("terminated_account_days", settings.TERMINATED_ACCOUNT_DAYS)

        # Checks if any users are no longer terminated and resets their processed status.
        reset_user_count = self.reevaluate_processed_users(terminated_account_days)

        # Retrieves actionable terminated users
        actionable_terminated_users = self.get_actionable_terminations(terminated_account_days)

        # Get graph token
        token = ms_graph_client_token()

        # Remove licenses from users
        if options.get("remove_licenses", False):
            success_count, failure_count, termination_summary = self.remove_user_licenses(actionable_terminated_users, token, send_failure_email=options.get("send_failure_email", False))

            # Summarize the management command actions
            self.summarize_results(
                success_count = success_count,
                failure_count = failure_count,
                reset_count = reset_user_count,
                actionable_terms_count = len(actionable_terminated_users),
                summary = termination_summary,
                send_summary_email = options.get("send_summary_email", False),
            )
        self.logger.info("Termination processing command complete...")


    def reevaluate_processed_users(self, terminated_account_days: int) -> int:
        """
        Finds all users who've been processed but are no longer terminated, and reverts their 'termination_processed' status.
        Handles users that have left and become re-employed before their departmentuser record was deleted.
        Separated into own method for testing ease.
        """
        users_reset = 0
        self.logger.info("Checking previously processed users for new job records...")

        processed_users = DepartmentUser.objects.filter(termination_processed=True)
        for user in processed_users:
            if not user.terminated_and_beyond_grace_period(terminated_account_days):
                user.termination_processed = False
                user.save()
                users_reset += 1
                self.logger.info(f"{user.email} is no longer terminated, termination_processed reset.")

        self.logger.info(f"Check complete: {users_reset} user(s) termination_processed status reset")

        return users_reset

    def get_actionable_terminations(self,terminated_account_days: int) -> list[DepartmentUser]:
        """
        Retrieves users that are terminated, passed their grace period, and haven't already been processed.
        """
        self.logger.info(f"Finding unprocessed users terminated over {terminated_account_days} days ago...")
        actionable_terminated_users = [user for user in DepartmentUser.objects
                                       .exclude(term_date_data__iexact="[]")
                                       .exclude(termination_processed=True) 
                if user.terminated_and_beyond_grace_period(terminated_account_days)
                ]
        self.logger.info(f"{len(actionable_terminated_users)} actionable terminations found.")
        return actionable_terminated_users


    def remove_user_licenses(self,users: list[DepartmentUser], token: dict, send_failure_email: bool=False) -> tuple[int,int,dict[str,list[str]]]:
        """
        Removes all licenses from specified users by removing them from azure license enabled groups.
        Returns a tuple of success_count: int, failure_count: int, termination_record: dict[email: str, groups_removed_from: list[str]]
        """
        termination_record = {}
        success_count = 0
        failure_count = 0
        for user in users:
            try:
                # Remove licenses
                if user.azure_guid is not None:
                    removed_groups = ms_graph_remove_user_licenses(user.azure_guid,token)
                    if removed_groups is not None:
                        # Record termination details
                        termination_record[user.email] = removed_groups
                        # Mark as processed
                        user.termination_processed = True
                        user.save()
                        success_count += 1
                        self.logger.info(f"{user.email}: Removed from groups [{", ".join(removed_groups)}]")
                    else:
                        raise Exception(f"Failed to remove licenses from user '{user.email}': Failed to acquire graph token.")
                else:
                    raise KeyError(f"Failed to remove licenses from user '{user.email}': User's azure_guid was empty. Set termination_processed to 'True' if termination processing is not required.")
            except Exception as e:
                failure_count +=1
                self.logger.exception(f"Exception raised during termination processing of '{user.email}'", exc=e)
                if send_failure_email:
                    subject = f"TERMINATED USERS HANDLING: exception during termination processing {user.email}"
                    message = f"User - {user.email}\nException:\n{str(e)}\n"
                    html_message = f"<p>User - {user.email}</p><p>Exception:</p><p>{str(e)}\n</p>"
                    mail.send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.NOREPLY_EMAIL,
                        recipient_list=settings.ADMIN_EMAILS,
                        html_message=html_message,
                        fail_silently=True,
                    )

        return success_count, failure_count, termination_record

    def summarize_results(self,success_count: int, failure_count: int, reset_count: int, actionable_terms_count: int, summary: dict, send_summary_email: bool):
        """
        Summarizes results for the command. If send_sumamry_email is set to true, the summary is sent to admins with a json file attachment of the record of terminations.
        Separated into it's own function for easier testing.
        """
        text_summary = f"""Terminationed processing complete
    SUMMARY:
    - Users reset to unprocessed: {reset_count},
    - Actionable terminations: {actionable_terms_count},
    - Terminations processed successfully: {success_count},
    - Terminations processed unsuccessfully: {failure_count}"""
        self.logger.info(text_summary)

        if send_summary_email:
            self.logger.info("Sending summary email...")
            html_summary = f"""SUMMARY:<br>
    - Users reset to unprocessed: {reset_count},<br>
    - Actionable terminations: {actionable_terms_count},<br>
    - Terminations processed successfully: {success_count},<br>
    - Terminations processed unsuccessfully: {failure_count}"""
            subject = f"Termination Processing Summary"
            msg = mail.EmailMultiAlternatives(
                subject=subject,
                body=text_summary,
                from_email=settings.NOREPLY_EMAIL,
                to=settings.ADMIN_EMAILS,
                attachments=[(f"terminations.json", json.dumps(summary),"application/json")]
            )
            msg.attach_alternative(html_summary, "text/html")
            msg.send(fail_silently=False)