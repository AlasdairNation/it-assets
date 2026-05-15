from django.conf import settings
from django.core.mail import EmailMultiAlternatives

def send_user_deletion_email(system_name, field_name, field_value):
        text_content = f"""Hi,\n
                This is an automated email to notify you of the deletion of an IT System Register user contact.\n
                System: {system_name}
                Field: {field_name}
                User: {field_value}

                Regards,\n
                OIM Service Desk\n"""
        html_content = f"""<p>Hi,</p>
                <p>This is an automated email to notify you of the deletion of an IT System Register user contact.</p>
                <ul>
                <li>System: {system_name}</li>
                <li>Field: {field_name}</li>
                <li>User: {field_value}</li>
                </ul>
                <p>Regards,</p>
                <p>OIM Service Desk</p>"""
        subject = f"IT System Register - User Contact Deletion - {system_name}"
        notify(subject=subject,body=text_content, html_body=html_content)

def send_daily_audit_email(flagged_users):
        subject = "IT Systems Register - Flagged Users"
        text_content_header = "Hi,\n This is an automated email to notify you of IT Systems Register contacts flagged as missing from address book.\n"
        html_content_header = "<p>Hi,</p><p>This is an automated email to notify you of T Systems Register contacts flagged as missing from address book.</p>"

        text_content_footer = "Regards,\nOIM Service Desk\n"
        html_content_footer = "<p>Regards,</p><p>OIM Service Desk</p>"
        text_content_body = ""
        html_content_body = ""
        for flagged_user in flagged_users:
                text_content_body += f""""
                        System: {flagged_user.system_name}
                        Field: {flagged_user.field_name}
                        User: {flagged_user.field_value}
                        Status: {flagged_user.user_status}
                        \n\n
                        """
                html_content_body += f"""
                        <ul>
                        <li>System: {flagged_user.system_name}</li>
                        <li>Field: {flagged_user.field_name}</li>
                        <li>User: {flagged_user.field_value}</li>
                        <li>Status: {flagged_user.user_status}</li>
                        </ul>
                        <br><br>
                        """
        text_body = text_content_header + text_content_body + text_content_footer
        html_body = html_content_header + html_content_body + html_content_footer
        notify(subject=subject, body=text_body, html_body= html_body)

def notify(subject,body,html_body):
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=[settings.NOREPLY_EMAIL],
            to=[settings.IT_SYSTEMS_REGISTER_EMAIL],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        return