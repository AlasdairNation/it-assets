import logging

from django.core.management.base import BaseCommand

from organisation.models import DepartmentUser
from itsystems.models import ITSystemRecord
from itsystems.notifications import send_daily_audit_email


class Command(BaseCommand):
    help = "Checks the IT Systems Register for disabled / addressbook excluded accounts in contacts, and notifies the ITPnP Mailbox"

    def add_arguments(self, parser):
        parser.add_argument(
            "-e",
            "--send-email",
            action="store_true",
            dest="send_email",
            help="(Optional) Flag to send notification emails to managers (default behaviour is logging only)",
        )

    def handle(self, *args, **options):
        logger = logging.getLogger("it_systems_register")
        logger.info("Contact audit operation started")

        # Get a list of active, licenced accounts for which we have a 'last sign-in' value.
        register = ITSystemRecord.objects.all()

        flagged_users = []
        for record in register:
            
            logger.info("processing system: " + str(record))
            if record.business_service_owner:
                _process_contact(flagged_users=flagged_users, record=record,field_name="Business Service Owner", user=record.business_service_owner, logger=logger)
            if record.system_owner:
                _process_contact(flagged_users=flagged_users, record=record, field_name="System Owner", user=record.system_owner, logger=logger)
            if record.technology_custodian:
                _process_contact(flagged_users=flagged_users, record=record,field_name="Technology Custodian", user=record.technology_custodian, logger=logger)
            if record.information_custodian:
                _process_contact(flagged_users=flagged_users, record=record,field_name="Information Custodian", user=record.information_custodian, logger=logger)
        
        num_flagged_users = len(flagged_users)
        logger.info(f"{num_flagged_users} Contacts flagged as hidden from the address book")

        if len(num_flagged_users>0):
            if options["send_email"]:
                logger.info("Sending contact audit email")
                send_daily_audit_email(flagged_users=flagged_users)
        
        logger.info("Contact audit operation complete")


def _process_contact(flagged_users, record, field_name, user, logger):
    if user.account_type in DepartmentUser.ACCOUNT_TYPE_EXCLUDE:
        system_str = str(record)
        user_str = str(user)
        status_str = user.get_account_type_display()
        flagged_users.append({"System":system_str, "Field":field_name,"User":user_str, "Status":status_str})
        logger.info("User Flagged - {system_str} | {field_name} | {user_str} | {status_str}")