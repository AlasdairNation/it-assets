from datetime import date, datetime

from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, View
from django.http import HttpResponse
from django.db.models import Q

from itassets.utils import get_next_pages, get_previous_pages

from .models import ITSystemRecord
from .csv_handling import ExportCSV, ImportCSV

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
        # Pass in any query string.
        if "q" in self.request.GET:
            context["query_string"] = self.request.GET["q"]
        context["object_count"] = len(self.get_queryset())
        context["previous_pages"] = get_previous_pages(context["page_obj"])
        context["next_pages"] = get_next_pages(context["page_obj"])
        return context
    
    def get_queryset(self):
        queryset = (
            ITSystemRecord.objects.all()
            .select_related(
                "division",
            )
        )

        # Filter the queryset, if required.
        if "q" in self.request.GET and self.request.GET["q"]:
            query_str = self.request.GET["q"]
            queryset = queryset.filter(
                Q(system_id__icontains=query_str)
                | Q(name__icontains=query_str)
                | Q(description__icontains=query_str)
            )

        queryset = queryset.order_by("system_id")

        return queryset
    
class ExportRegisterAsCSV(LoginRequiredMixin, View):
    """A custom view to return a representation of the IT Systems Register as a csv"""
    def get(self, request, *args, **kwargs):
        # Creates a http response to hold the CSV
        attachment_header = 'attachment; filename="it_systems_register_' + str(date.today().isoformat()) + '_' + str(datetime.now().strftime('%H%M')) + '.csv"'
        response = HttpResponse(
            content_type="text/csv",
            headers={"Content-Disposition":attachment_header}
        )
        # Writes register to the response as a CSV
        ExportCSV(response)
        return response

class ImportRegisterChangesFromCSV(LoginRequiredMixin, View):
    """A custom view to allow the user to import changes to the IT Systems Register via a csv"""

    # Displays the initial file upload form
    def get(self, request, *args, **kwargs):
        response = render(request, "admin/itsystems/itsystemrecord/upload_csv.html")
        return response

    # Processes CSV and displays results to the user
    # If the import is successful it displays the results, otherwise it displays an error message in the file upload form
    def post(self, request, *args, **kwargs):
        # Imports CSV, returning results
        results = ImportCSV(request)

        if results['validation']['valid']:
            # Displays results
            response = render(request, "admin/itsystems/itsystemrecord/results.html", context = results)
        else:
            print(results['validation'])
            # Displays error message
            response = render(request, "admin/itsystems/itsystemrecord/upload_csv.html", context = results['validation'])
        return HttpResponse(response)