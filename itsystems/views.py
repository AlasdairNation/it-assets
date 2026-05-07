import json
from datetime import date, datetime

from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, View
from django.db.models import Q
from django.conf import settings
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django.core.exceptions import ObjectDoesNotExist

from itassets.utils import get_next_pages, get_previous_pages

from .models import ITSystemRecord, Status, Division, Seasonality, Availability, Sensitivity, SystemType
from .utils import export_csv, import_csv, retrieve, replace_contact


class ITSystemsRegister(LoginRequiredMixin, ListView):
    """A custom user facing view to display the IT Systems Register"""

    template_name = "itsystems/it_systems_register.html"
    model = ITSystemRecord
    paginate_by = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_title"] = "Office of Information Management"
        context["site_acronym"] = "OIM"
        context["page_title"] = "IT Systems Register"

        # Retrieve all choice fields
        context["statuses"] = Status.objects.all()
        context["divisions"] = Division.objects.all()
        context["seasonalities"] = Seasonality.objects.all()
        context["availabilities"] = Availability.objects.all()
        context["sensitivities"] = Sensitivity.objects.all()
        context["system_types"] = SystemType.objects.all()

        # Pass in any search & filtering data
        if "q" in self.request.GET:
            context["query_string"] = self.request.GET["q"]
        if "status" in self.request.GET:
            context["status_filter"] = retrieve(Status, self.request.GET["status"])
        if "division" in self.request.GET:
            context["division_filter"] = retrieve(Division, self.request.GET["division"])
        if "seasonality" in self.request.GET:
            context["seasonality_filter"] = retrieve(Seasonality, self.request.GET["seasonality"])
        if "availability" in self.request.GET:
            context["availability_filter"] = retrieve(Availability, self.request.GET["availability"])
        if "vital_records" in self.request.GET:
            context["vital_records_filter"] = self.request.GET["vital_records"]
        if "sensitivity" in self.request.GET:
            context["sensitivity_filter"] = retrieve(Sensitivity, self.request.GET["sensitivity"])
        if "system_type" in self.request.GET:
            context["system_type_filter"] = retrieve(SystemType, self.request.GET["system_type"])

        context["object_count"] = len(self.get_queryset())
        context["previous_pages"] = get_previous_pages(context["page_obj"])
        context["next_pages"] = get_next_pages(context["page_obj"])
        return context

    def get_queryset(self):
        queryset = ITSystemRecord.objects.all()

        # Filters queryset by chosen search values and filter values
        if self.request.GET.get("status"):
            queryset = queryset.filter(status__id=self.request.GET["status"])
        if self.request.GET.get("division"):
            queryset = queryset.filter(division__id=self.request.GET["division"])
        if self.request.GET.get("seasonality"):
            queryset = queryset.filter(seasonality__id=self.request.GET["seasonality"])
        if self.request.GET.get("availability"):
            queryset = queryset.filter(availability__id=self.request.GET["availability"])
        if self.request.GET.get("vital_records"):
            queryset = queryset.filter(vital_records=(self.request.GET["vital_records"] == "True"))
        if self.request.GET.get("sensitivity"):
            queryset = queryset.filter(sensitivity__id=self.request.GET["sensitivity"])
        if self.request.GET.get("system_type"):
            queryset = queryset.filter(system_type__id=self.request.GET["system_type"])
        if "q" in self.request.GET and self.request.GET["q"]:
            query_str = self.request.GET["q"]
            queryset = queryset.filter(
                Q(system_id__icontains=query_str) | Q(name__icontains=query_str) | Q(description__icontains=query_str)
            )

        queryset = queryset.order_by("system_id")

        return queryset


class ExportRegisterAsCSV(LoginRequiredMixin, View):
    """A custom view to return a representation of the IT Systems Register as a csv"""

    def get(self, request, *args, **kwargs):
        # Creates a http response to hold the CSV
        attachment_header = (
            'attachment; filename="it_systems_register_'
            + str(date.today().isoformat())
            + "_"
            + str(datetime.now().strftime("%H%M"))
            + '.csv"'
        )
        response = HttpResponse(content_type="text/csv", headers={"Content-Disposition": attachment_header})
        # Writes register to the response as a CSV
        export_csv(response)
        return response


class ImportRegisterChangesFromCSV(LoginRequiredMixin, PermissionRequiredMixin, View):
    """A custom view to allow the user to import changes to the IT Systems Register via a csv"""

    # Permissions locked to people that can already edit the register
    permission_required = ["itsystems.change_itsystemrecord", "itsystems.add_itsystemrecord"]

    # Displays the initial file upload form
    def get(self, request, *args, **kwargs):
        response = render(request, "admin/itsystems/itsystemrecord/upload_csv.html")
        return response

    # Processes CSV and displays results to the user
    # If the import is successful it displays the results, otherwise it displays an error message in the file upload form
    def post(self, request, *args, **kwargs):
        # Imports CSV, returning results
        results = import_csv(request)

        if results["validation"]["valid"]:
            # Displays results
            response = render(request, "admin/itsystems/itsystemrecord/results.html", context=results)
        else:
            print(results["validation"])
            # Displays error message
            response = render(request, "admin/itsystems/itsystemrecord/upload_csv.html", context=results["validation"])
        return response
    

class ITSystemRecordAPIResource(View):
    """An API view that returns JSON of the IT System Register"""

    @method_decorator(cache_control(max_age=settings.API_RESPONSE_CACHE_SECONDS, private=True))
    def get(self, request, *args, **kwargs):
        response = None
        try:
            queryset = (
                ITSystemRecord.objects.all()
                .select_related(
                    "status",
                    "division",
                    "seasonality",
                    "availability",
                    "sensitivity",
                    "system_type"
                )
                .order_by("system_id")
            )

            # Queryset filtering.
            if "system_id" in kwargs and kwargs["system_id"]:  # Allow filtering by object system_id.
                queryset = queryset.filter(system_id=kwargs["system_id"])

            else:  # Normal API response.
                register = [record.to_dict() for record in queryset]

            response = JsonResponse(register, safe=False)

        except UnboundLocalError as e:
            if "system_id" in kwargs and kwargs["system_id"]:
                response = HttpResponseBadRequest("Can't find system " + kwargs["system_id"] + ": " + str(e))
            else:
                response = HttpResponseBadRequest(str(e))
        return response
    
    @method_decorator(cache_control(max_age=settings.API_RESPONSE_CACHE_SECONDS, private=True))
    def post(self, request, *args, **kwargs):
        """An API view that allows users to update a record or a contact"""

        response = None

        if "system_id" in kwargs and kwargs["system_id"]:  # Allow filtering by object system_id.
            system_id = system_id=kwargs["system_id"]
            try:
                old_record = ITSystemRecord.objects.get(system_id=system_id)
                data = json.loads(request.POST)
                force = data.get('force')==True
                new_record = data.get('record')
                old_record.set_from_dict(dict=new_record, plain_text=True, force=force)
                old_record.save()
                response = JsonResponse(dict=old_record.to_dict(), save=False)
                
            except ITSystemRecord.DoesNotExist:
                response = HttpResponseBadRequest("Can't find system " + system_id)
            except json.JSONDecodeError:
                response = HttpResponseBadRequest("JSON data is invalid")
            except ObjectDoesNotExist as e:
                response = HttpResponseBadRequest("Failed to update system " + system_id + " : " + str(e))
            except Exception as e:
                response = HttpResponseBadRequest("Unexpected error: " + str(e))
                
        elif ("old_contact" in kwargs and kwargs["old_contact"]) and ("new_contact" in kwargs and kwargs["new_contact"]):
            changes = replace_contact(old_contact=kwargs["old_contact"], new_contact=kwargs["new_contact"])
            response = JsonResponse(changes, safe=False)
        else:
            response = HttpResponseBadRequest("Invalid request, please specify 'old_contact' and 'new_contact'")
        return response
            
