import csv
import io
import reversion
from .models import ITSystemRecord
from .models import DepartmentUser


def export_csv(response):
    """
    Exports the IT Systems Register to a csv, writing it into a HttpResponse object passed to it.
    """
    writer = csv.writer(response)
    headers = [field.name for field in __get_model_fields()]
    writer.writerow(headers)

    records = ITSystemRecord.objects.all()
    for record in records:
        record_vals = [
            record.system_id,
            record.name,
            record.status.name if record.status else "",
            record.division.name if record.division else "",
            record.business_service_owner.email if record.business_service_owner else "",
            record.system_owner.email if record.system_owner else "",
            record.technology_custodian.email if record.technology_custodian else "",
            record.information_custodian.email if record.information_custodian else "",
            record.seasonality.name if record.seasonality else "",
            record.availability.name if record.availability else "",
            record.link,
            record.description,
            record.file_store_link,
            record.vital_records,
            record.disposal_authority,
            record.retention_and_disposal,
            record.ubcs,
            record.sensitivity.name if record.sensitivity else "",
            record.system_type.name if record.system_type else "",
        ]
        writer.writerow(record_vals)


def import_csv(request):
    """
    Updates the IT System Register database from a csv contained within an Http Post Request.
    This function returns a dictionary containing the validation results and 3 lists respectively containing details of records created, records updated, and records that failed to process.
    """
    csv_file = request.FILES["csv_file"]
    force = request.POST["force"]=="True"
    update_list = []
    create_list = []
    failed_list = []

    validate_results = __validate_csv(csv_file)
    if validate_results["valid"]:
        raw_text = validate_results["raw_text"]
        record_list = list(csv.DictReader(io.StringIO(raw_text)))
        for record in record_list:
            force_failures = []
            # Search for existing record in database
            try:
                found_record = ITSystemRecord.objects.get(system_id=record["system_id"])
            except ITSystemRecord.DoesNotExist:
                found_record = None 

            try:
                # Populate new record with data
                new_record = ITSystemRecord()
                force_failures = new_record.set_from_dict(dict=record, plain_text=True, force=force)

                if found_record:
                    changes = found_record.compare(new_record)
                    if len(changes) > 0:
                        with reversion.create_revision():
                            # Update Record
                            force_failures = found_record.set_from_dict(dict=record, plain_text=True, force=force)
                            found_record.modified_by = request.user.email
                            found_record.save()

                            # Create comment for version history
                            change_log = "Changed via CSV: "
                            for change in changes:
                                change_log += change["verbose_field"] + ", "
                            comment = change_log[:-2] + "."

                            # Create version history entry
                            reversion.set_user(request.user)
                            reversion.set_comment(comment)

                        update_list.append({"record": found_record.system_id_name, "changes": changes})
                elif not found_record:
                    with reversion.create_revision():
                        # Create Record
                        new_record.created_by = request.user.email
                        new_record.modified_by = request.user.email
                        new_record.save()

                        # Create version history entry
                        reversion.set_user(request.user)
                        reversion.set_comment("Created via CSV import.")
                    changes = new_record.compare(None)
                    create_list.append({"record": new_record.system_id_name, "changes": changes})
                
                if len(force_failures)>0:
                    error_message = "Partial Failure(s): " + "\r\n".join(force_failures)
                    failed_list.append({"record": record["system_id"], "changes": error_message})

            except Exception as e:
                if hasattr(e, "message"):
                    error_message = e.message
                else:
                    error_message = str(e)
                failed_list.append({"record": record["system_id"], "changes": error_message})

    return {
        "validation": {"valid": validate_results["valid"], "message": validate_results["message"]},
        "created": create_list,
        "updated": update_list,
        "failed": failed_list,
    }


def retrieve(cls, id):
    """
    Retrieves a record using an Id from an inputted class.
    """
    try:
        model = cls.objects.get(id=id)
    except Exception:
        model = None
    return model


def replace_contact(old_contact,new_contact):
    records = ITSystemRecord.objects.all()
    changes = []

    try:
        old_contact_fk = DepartmentUser.objects.get(email=old_contact)
    except DepartmentUser.DoesNotExist:
        old_contact_fk = None
    try:
        new_contact_fk = DepartmentUser.objects.get(email=new_contact)
    except DepartmentUser.DoesNotExist:
        old_contact_fk = None
    
    if old_contact_fk and new_contact_fk:
        for record in records:
            record_changes = []
            if record.business_service_owner == old_contact_fk:
                record.business_service_owner = new_contact_fk
                record_changes.append("business_service_owner")
            if record.system_owner == old_contact_fk:
                record.system_owner = new_contact_fk
                record_changes.append("system_owner")
            if record.technology_custodian == old_contact_fk:
                record.technology_custodian = new_contact_fk
                record_changes.append("technology_custodian")
            if record.information_custodian == old_contact_fk:
                record.information_custodian = new_contact_fk
                record_changes.append("information_custodian")
            
            if len(record_changes)>0:
                try:
                    record.save()
                    changes.append({'record':record.system_id,'success':True, 'changes':record_changes})
                except Exception as e:
                    changes.append({'record':record.system_id,'success':False, 'changes':str(e)})
    return changes


def __validate_csv(csv_file):
    """
    Validates that passed-in file is a csv file, has the correct headers, and is under 2mb.
    Results are passed back as a dictionary containing a validation boolean and an error message for display
    """
    valid = False
    msg = ""
    raw_text = None
    # Checks that file is a CSV
    if csv_file.name.endswith(".csv"):
        # Checks that file isn't chunked / over 2 mb
        if not csv_file.multiple_chunks():
            raw_text = csv_file.read().decode(encoding="utf-8", errors="replace")
            csv_headers = raw_text.splitlines()[0].split(",")
            model_fields = __get_model_fields()
            # Checks that csv has the correct headers
            if all(csv == model.name for csv, model in zip(csv_headers, model_fields)):
                valid = True
                msg = "CSV is Valid"
            else:
                msg = "CSV Headers do not match the required format"
        else:
            msg = "File size is too large (>2MB)."
    else:
        msg = "The selected file isn't a CSV"
    return {"valid": valid, "message": msg, "raw_text": raw_text}


def __get_model_fields():
    """
    Retrieves data-entry relevant fields of the ITSystemRecord class
    """
    return ITSystemRecord._meta.get_fields()[1:-4]
