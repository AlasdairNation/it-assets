import logging, json
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core import mail
from django.test import TestCase, override_settings
from mixer.backend.django import mixer
from psycopg import errors

from organisation.management.commands.department_users_terminated_users_handling import Command
from organisation.management.commands.organisation_generate_dummy_data import DIVISION_NAMES, EMP_STATUS
from organisation.models import CostCentre, DepartmentUser, Location

# Disable non-critical logging output.
logging.disable(logging.CRITICAL)


class TerminatedUsersTestCase(TestCase):
    def setUp(self) -> None:
        # 1 user not-term, 1 user term, 1 user post-grace term.
        self.user_not_terminated = create_test_user(
            [
                {
                    "term_date": (datetime.now(tz=settings.TZ).date() + timedelta(weeks=4)).strftime("%Y-%m-%d"),
                }
            ]
        )
        self.user_not_terminated.save()
        self.user_terminated = create_test_user(
            [
                {
                    "term_date": datetime.now(tz=settings.TZ).date().strftime("%Y-%m-%d"),
                }
            ]
        )
        self.user_terminated.save()
        self.user_terminated_after_grace = create_test_user(
            [
                {
                    "term_date": (datetime.now(tz=settings.TZ).date() + timedelta(weeks=-4)).strftime("%Y-%m-%d"),
                }
            ]
        )
        self.user_terminated_after_grace.save()
        self.user_terminated_then_rehired = create_test_user(
            [
                {
                    "term_date": (datetime.now(tz=settings.TZ).date() + timedelta(weeks=-4)).strftime("%Y-%m-%d"),
                },
                {
                    "term_date": None,
                },
            ]
        )
        self.user_terminated_then_rehired.save()

        self.cmd = Command()


    def test_get_actionable_terminations(self):
        """
        Validates that get_actionable_terminations retrieves only unprocessed terminated users over the grace period.
        """
        # Validates that only the terminated user is retrieved
        terminations = self.cmd.get_actionable_terminations(terminated_account_days=14)
        self.assertIn(self.user_terminated_after_grace, terminations)
        self.assertEqual(len(terminations),1)
        self.assertEqual(self.user_terminated_after_grace.termination_processed,False)
        self.user_terminated_after_grace.termination_processed = True
        self.user_terminated_after_grace.save()

        # Validates that processed users are skipped
        terminations = self.cmd.get_actionable_terminations(terminated_account_days=14)
        self.assertEqual(len(terminations),0)

        # Validates multi user retrieval and variable grace period setting
        self.user_terminated_after_grace.termination_processed = False
        self.user_terminated_after_grace.save()
        terminations = self.cmd.get_actionable_terminations(terminated_account_days=0)
        self.assertIn(self.user_terminated_after_grace, terminations)
        self.assertIn(self.user_terminated, terminations)
        self.assertEqual(len(terminations),2)

        # Validates that processed user is skipped and unprocessed is returned
        self.user_terminated.termination_processed = True
        self.user_terminated.save()
        terminations = self.cmd.get_actionable_terminations(terminated_account_days=0)
        self.assertIn(self.user_terminated_after_grace, terminations)
        self.assertEqual(len(terminations),1)
        self.assertEqual(self.user_terminated_after_grace.termination_processed,False)

    def test_reevaluated_processed_users(self):
        """
        Evaluates that users who are marked as processed are unmarked if they are no longer terminated
        """

        self.assertEqual(len(DepartmentUser.objects.filter(termination_processed=True)),0)

        # User should not be unmarked
        self.user_terminated_after_grace.termination_processed = True
        self.user_terminated_after_grace.save()

        # User SHOULD be unmarked - Unterminated
        self.user_terminated_then_rehired.termination_processed = True
        self.user_terminated_then_rehired.save()

        # user SHOULD be unmarked - Within grace period
        self.user_terminated.termination_processed = True
        self.user_terminated.save()

        # Evaluates that only those terminated and past their grace period aren't reset.
        self.assertEqual(len(DepartmentUser.objects.filter(termination_processed=True)),3)
        reset_user_count = self.cmd.reevaluate_processed_users(14)
        processed_users = DepartmentUser.objects.filter(termination_processed=True)
        self.assertEqual(len(processed_users),1)
        self.assertEqual(reset_user_count,2)
        self.assertIn(self.user_terminated_after_grace, processed_users)

    @patch("organisation.management.commands.department_users_terminated_users_handling.ms_graph_remove_user_licenses")
    def test_remove_user_licenses_reporting(self, mock_remove_licenses):
        """
        Tests that users have their removed groups accurately summarized, and ms_graph_remove_user_licenses to called on each.
        """
        a_groups =  ["A_removed_group1","A_removed_group2"]
        b_groups = ["B_removed_group1"]
        c_groups = []
        mock_remove_licenses.side_effect = [a_groups,b_groups,c_groups]
        success_count, failure_count, termination_record = self.cmd.remove_user_licenses(
            users=[
                self.user_terminated_after_grace,
                self.user_terminated, 
                self.user_terminated_then_rehired,
            ],
            token={},
            send_failure_email=False
            )
        self.assertEqual(mock_remove_licenses.call_count,3)
        self.assertEqual(success_count,3)
        self.assertEqual(failure_count,0)
        self.assertEqual(len(termination_record), 3)
        self.assertTrue(self.user_terminated_after_grace.email in termination_record)
        self.assertEqual(termination_record[self.user_terminated_after_grace.email],a_groups)
        self.assertTrue(self.user_terminated.email in termination_record)
        self.assertEqual(termination_record[self.user_terminated.email],b_groups)
        self.assertTrue(self.user_terminated_then_rehired.email in termination_record)
        self.assertEqual(termination_record[self.user_terminated_then_rehired.email],c_groups)

    @patch("organisation.management.commands.department_users_terminated_users_handling.ms_graph_remove_user_licenses")
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend") # prevents email sending and allows for mails to be read and validated in testing
    def test_remove_user_licenses_exceptions_and_emails(self, mock_remove_licenses):
        """
        Validates that exceptions are handled properly and email contents is properly formatted
        """
        # Should fail on all but user_terminated_then_rehired.
        b_groups = None # emulates token acquisition failure
        c_groups = ["C_removed_group1","C_removed_group2"] # Should succeed
        mock_remove_licenses.side_effect = [b_groups, c_groups]
        self.user_terminated_after_grace.azure_guid = None # Will trigger KeyError
        self.user_terminated_after_grace.save()

        success_count, failure_count, termination_record = self.cmd.remove_user_licenses(
            users=[
                self.user_terminated_after_grace,
                self.user_terminated, 
                self.user_terminated_then_rehired,
            ],
            token={},
            send_failure_email=True
            )
        # Logical flow validation
        self.assertEqual(mock_remove_licenses.call_count,2) # Fails inside second call
        self.assertEqual(success_count,1)
        self.assertEqual(failure_count,2)
        self.assertEqual(len(termination_record), 1)
        self.assertEqual(termination_record[self.user_terminated_then_rehired.email],c_groups)

        # Mail content validation
        self.assertEqual(len(mail.outbox),2)
        first_mail = mail.outbox[0]
        second_mail = mail.outbox[1]

        self.assertTrue(self.user_terminated_after_grace.email in first_mail.body)
        self.assertTrue(self.user_terminated_after_grace.email in first_mail.subject)
        self.assertTrue("azure_guid" in first_mail.body)

        self.assertTrue(self.user_terminated.email in second_mail.body)
        self.assertTrue(self.user_terminated.email in second_mail.subject)
        self.assertTrue("token" in second_mail.body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend") # prevents email sending and allows for mails to be read and validated in testing
    def test_summarize_results(self):
        """
        Validates that the summary email accurately reports stats and attaches the summary properly
        """
        summary_data = {"example_user@user.com":["blah","blah2"]}
        self.cmd.summarize_results(
            success_count=1001,
            failure_count=2002,
            reset_count=3003,
            actionable_terms_count=4004,
            summary=summary_data,
            send_summary_email=True
        )
        self.assertEqual(len(mail.outbox),1)
        summary_mail = mail.outbox[0]
        self.assertEqual(summary_mail.subject, "Termination Processing Summary")
        self.assertIn(f"unprocessed: 3003" ,summary_mail.body)
        self.assertIn(f"terminations: 4004" ,summary_mail.body)
        self.assertIn(f"successfully: 1001" ,summary_mail.body)
        self.assertIn(f"unsuccessfully: 2002" ,summary_mail.body)
        file = summary_mail.attachments[0]
        self.assertEqual(json.loads(file.content),summary_data)
        self.assertTrue(file.filename.endswith(".json"))
        

# Creates a DepartmentUser object for testing
def create_test_user(term_date_data) -> DepartmentUser:
    return mixer.blend(
        DepartmentUser,
        active=True,
        email=mixer.RANDOM,
        given_name=mixer.RANDOM,
        surname=mixer.RANDOM,
        employee_id=mixer.RANDOM,
        dir_sync_enabled=True,
        azure_guid=mixer.RANDOM,
        term_date_data=term_date_data,
    )


class GenerateDummyDataTestCase(TestCase):
    """Test the organisation_generate_dummy_data management command."""

    @override_settings(DEBUG=False)
    def test_command_refuses_when_not_debug(self):
        """Command raises CommandError and creates nothing when DEBUG=False."""
        with self.assertRaises(CommandError):
            call_command("organisation_generate_dummy_data")
        self.assertEqual(Location.objects.count(), 0)
        self.assertEqual(CostCentre.objects.count(), 0)
        self.assertEqual(DepartmentUser.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_generates_default_counts(self):
        """DEBUG=True with default options creates 5 locations, 5 cost centres, 20 users with valid data."""
        out = StringIO()
        call_command("organisation_generate_dummy_data", stdout=out)
        self.assertEqual(Location.objects.count(), 5)
        self.assertEqual(CostCentre.objects.count(), 5)
        self.assertEqual(DepartmentUser.objects.count(), 20)
        self.assertIn("Created 5 locations, 5 cost centres and 20 department users", out.getvalue())
        for u in DepartmentUser.objects.all():
            self.assertIsNotNone(u.cost_centre)
            self.assertIsNotNone(u.location)
            self.assertIsNotNone(u.account_type)
            self.assertTrue(u.ascender_data)
            self.assertIn(u.ascender_data["emp_status"], EMP_STATUS)
            self.assertIn(u.ascender_data["clevel2_desc"], DIVISION_NAMES)
            self.assertTrue(u.get_division())
        self.assertEqual(DepartmentUser.objects.values("email").distinct().count(), 20)
        self.assertEqual(DepartmentUser.objects.filter(manager__isnull=True).count(), 1)
        self.assertTrue(CostCentre.objects.filter(manager__isnull=False).exists())
        for loc in Location.objects.all():
            self.assertIsNotNone(loc.point)

    @override_settings(DEBUG=True)
    def test_generates_custom_counts(self):
        """DEBUG=True with custom --locations/--cost-centres/--department-users creates that many records."""
        call_command("organisation_generate_dummy_data", locations=2, cost_centres=3, department_users=7, stdout=StringIO())
        self.assertEqual(Location.objects.count(), 2)
        self.assertEqual(CostCentre.objects.count(), 3)
        self.assertEqual(DepartmentUser.objects.count(), 7)

    @override_settings(DEBUG=True)
    def test_rejects_negative_counts(self):
        """Command raises CommandError when given a negative count."""
        with self.assertRaises(CommandError):
            call_command("organisation_generate_dummy_data", department_users=-1)

    def test_no_module_level_mixer_import(self):
        """The command module must not have a module-level mixer import."""
        import organisation.management.commands.organisation_generate_dummy_data as cmd

        self.assertFalse(hasattr(cmd, "mixer"))


class CheckCostCentreManagersTestCase(TestCase):
    """Tests for the check_cost_centre_managers management command.

    The Ascender view is mocked: each record is a row where index 1 is the cost centre code and
    index 6 is the manager's employee ID.
    """

    def setUp(self):
        self.cost_centre = mixer.blend(CostCentre, code="123456", ascender_code="123456", manager=None)
        self.manager = mixer.blend(DepartmentUser, employee_id="100001")
        self.other_user = mixer.blend(DepartmentUser, employee_id="100002")

    @staticmethod
    def record(cc_code, employee_id):
        return ["", cc_code, "", "", "", "", employee_id]

    @patch("organisation.management.commands.check_cost_centre_managers.ascender_cc_manager_fetch")
    def test_updates_cost_centre_manager(self, mock_fetch):
        """The matching cost centre manager is updated from Ascender data."""
        mock_fetch.return_value = [self.record(self.cost_centre.ascender_code, self.manager.employee_id)]

        call_command("check_cost_centre_managers")

        self.cost_centre.refresh_from_db()
        self.assertEqual(self.cost_centre.manager, self.manager)

    @patch("organisation.management.commands.check_cost_centre_managers.ascender_cc_manager_fetch")
    def test_skips_unknown_cost_centre_or_employee(self, mock_fetch):
        """Records with an unmatched cost centre or employee ID are skipped without error."""
        mock_fetch.return_value = [
            self.record("999999", self.manager.employee_id),  # Unknown cost centre.
            self.record(self.cost_centre.ascender_code, "999999"),  # Unknown employee.
        ]

        call_command("check_cost_centre_managers")

        self.cost_centre.refresh_from_db()
        self.assertIsNone(self.cost_centre.manager)

    @patch("organisation.management.commands.check_cost_centre_managers.ascender_cc_manager_fetch")
    def test_ascender_unavailable_raises_command_error(self, mock_fetch):
        """A transient Ascender failure results in a CommandError, not an unhandled traceback."""
        mock_fetch.side_effect = errors.FdwUnableToEstablishConnection(
            'connection for foreign table "cc_manager_view" cannot be established\nDETAIL:  ORA-12541: TNS:no listener'
        )

        with self.assertRaises(CommandError) as context:
            call_command("check_cost_centre_managers")

        self.assertIn("Ascender database is unavailable", str(context.exception))
        self.cost_centre.refresh_from_db()
        self.assertIsNone(self.cost_centre.manager)
