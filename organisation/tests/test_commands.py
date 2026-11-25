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
        self.user_not_terminated.update_from_ascender_term_data(save_after=True)
        self.user_terminated = create_test_user(
            [
                {
                    "term_date": (datetime.now(tz=settings.TZ) - timedelta(days=1)).date().strftime("%Y-%m-%d"),
                }
            ]
        )
        self.user_terminated.update_from_ascender_term_data(save_after=True)
        self.user_terminated_after_grace = create_test_user(
            [
                {
                    "term_date": (datetime.now(tz=settings.TZ).date() + timedelta(weeks=-4)).strftime("%Y-%m-%d"),
                }
            ]
        )
        self.user_terminated_after_grace.update_from_ascender_term_data(save_after=True)
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
        self.user_terminated_then_rehired.update_from_ascender_term_data(save_after=True)

        self.cmd = Command()

    @patch("organisation.management.commands.department_users_terminated_users_handling.DepartmentUser.disable_entra_account")
    @patch("organisation.management.commands.department_users_terminated_users_handling.Command.report_exception")
    def test_stage_terminated_staff(self, mock_report, mock_disable):
        """
        Validates that terminated unstaged users are accurately staged and disabled, and all other users are ignored.
        """
        # Validates users are unstaged and ready to be staged
        self.assertEqual(self.user_terminated_after_grace.offboarding_staged_at,None)
        self.assertEqual(self.user_terminated_after_grace.ongoing,False)
        self.assertEqual(self.user_terminated.offboarding_staged_at,None)
        self.assertEqual(self.user_terminated.ongoing,False)

        # faux stages a staff member yesterday
        self.user_terminated.offboarding_staged_at = datetime.now(tz=settings.TZ) - timedelta(days=2)
        self.user_terminated.save()
        # stages staff
        self.cmd.stage_terminated_staff(terminated_account_days=14, ticketing=False, failure_emails=False, token={})
        staged_staff = DepartmentUser.objects.filter(offboarding_staged_at__isnull=False)
        # validate that only terminated users are staged
        self.assertIn(self.user_terminated_after_grace, staged_staff)
        self.assertIn(self.user_terminated, staged_staff)
        self.assertEqual(len(staged_staff),2)
        # validate that the staging date is today
        self.user_terminated_after_grace = DepartmentUser.objects.get(email=self.user_terminated_after_grace.email)
        self.assertEqual(self.user_terminated_after_grace.offboarding_staged_at.date(),datetime.now(tz=settings.TZ).date())
        # validates that the staging date wasn't changed
        self.assertEqual(self.user_terminated.offboarding_staged_at.date(),(datetime.now(tz=settings.TZ) - timedelta(days=2)).date())
        # validates that only the staged user was disabled
        mock_disable.assert_called_once()
        # validates there were no handled errors
        mock_report.assert_not_called()

    @patch("organisation.management.commands.department_users_terminated_users_handling.Command.report_exception")
    def test_unstage_returning_staff(self, mock_report):
        # stages both terminated users
        # staged 2 days ago - But has returned
        self.user_terminated.offboarding_staged_at = datetime.now(tz=settings.TZ) - timedelta(days=2)
        self.user_terminated.ongoing = True
        self.user_terminated.termination_date = None
        self.user_terminated.save()
        # staged today
        self.user_terminated_after_grace.offboarding_staged_at = datetime.now(tz=settings.TZ)
        self.user_terminated_after_grace.save()
        
        # unstage users
        self.cmd.unstage_returning_staff(terminated_account_days=24, ticketing=False, failure_emails=False)
        staged_staff = DepartmentUser.objects.filter(offboarding_staged_at__isnull=False)

        # retrieve changes from DB
        self.user_terminated = DepartmentUser.objects.get(email=self.user_terminated.email)

        self.assertIn(self.user_terminated_after_grace, staged_staff)
        self.assertNotIn(self.user_terminated, staged_staff)
        self.assertEqual(len(staged_staff),1)
        # validate that the staging date is today
        self.assertEqual(self.user_terminated_after_grace.offboarding_staged_at.date(),datetime.now(tz=settings.TZ).date())
        # validates that the staging date wasn't changed
        self.assertEqual(self.user_terminated.offboarding_staged_at,None)

        # Asserts no errors occured
        mock_report.assert_not_called()

    def test_offboard_staged_staff(self):
        pass

    def test_report_exception(self):
        pass

    def test_ticket_management(self):
        pass
        

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
        ongoing=False,
        termination_date=None,
        offboarding_staged_at=None,
        offboarding_ticket_id=None,
        account_type=2
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
