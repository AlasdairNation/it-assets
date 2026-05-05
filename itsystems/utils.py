import csv
import io
import reversion
from .models import ITSystemRecord

def export_csv(response):
    """
    Exports the IT Systems Register to a csv, writing it into a HttpResponse object passed to it.
    """
    writer=csv.writer(response)
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
            record.system_type.name if record.system_type else ""
        ]
        writer.writerow(record_vals)

def import_csv(request):
    """
    Updates the IT System Register database from a csv contained within an Http Post Request.
    This function returns a dictionary containing the validation results and 3 lists respectively containing details of records created, records updated, and records that failed to process.
    """
    csv_file = request.FILES['csv_file']
    update_list = []
    create_list = []
    failed_list = []

    validate_results = __validate_csv(csv_file)
    if validate_results['valid']:
        raw_text = validate_results['raw_text']
        record_list = list(csv.DictReader(io.StringIO(raw_text)))
        for record in record_list:
            # Search for existing record in database
            try:
                found_record = ITSystemRecord.objects.get(system_id=record['system_id'])
            except ITSystemRecord.DoesNotExist as e: 
                found_record = None
        
            try:
                # Populate new record with data
                new_record = ITSystemRecord()
                new_record.set_from_dict(record)

                if found_record:
                    changes = found_record.compare(new_record)
                    if len(changes)>0:
                        with reversion.create_revision():
                            # Update Record
                            found_record.set_from_dict(record)
                            found_record.modified_by = request.user.email
                            found_record.save()

                            # Create comment for version history
                            change_log = "Changed via CSV: "
                            for change in changes:
                                change_log += change['verbose_field'] + ', '
                            comment = change_log[:-2] + "."

                            # Create version history entry
                            reversion.set_user(request.user)
                            reversion.set_comment(comment)

                        update_list.append({"record":found_record.system_id_name, "changes":changes})
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
                    create_list.append({"record":new_record.system_id_name, "changes":changes})
            except Exception as e:
                if hasattr(e, 'message'):
                    error_message = e.message
                else:
                    error_message = str(e)
                failed_list.append({"record":record['system_id'], "changes": error_message})

    return {'validation':{'valid':validate_results['valid'], 'message':validate_results['message']},'created':create_list,'updated':update_list, 'failed':failed_list}


def retrieve(cls, id):
    try:
        model = cls.objects.get(id=id)
    except Exception:
        model = None
    return model


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
            raw_text = csv_file.read().decode(encoding='utf-8', errors='replace')
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
    return {"valid":valid, "message":msg, "raw_text":raw_text}

def __get_model_fields():
    """
    Retrieves data-entry relevant fields of the ITSystemRecord class
    """
    return ITSystemRecord._meta.get_fields()[1:-4]