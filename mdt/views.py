import json
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.db import transaction

from .models import (
    Patient, ClinicalDetails, MDTConsensus, State, District, PrimarySite,
    BloodInvestigation, ImagingInvestigation, PathologyInvestigation, MolecularInvestigation,
    AuditLog, UserProfile
)
from .forms import (
    PatientForm, ClinicalDetailsForm, MDTConsensusForm,
    BloodInvestigationForm, ImagingInvestigationForm, PathologyInvestigationForm, MolecularInvestigationForm
)
from .services import (
    generate_next_mdt_id, write_audit_log, cascade_diagnosis, get_consolidated_investigations
)


# ==========================================
# Authentication & Dashboard
# ==========================================

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        uname = request.POST.get('username', '').strip()
        pword = request.POST.get('password', '').strip()
        user = authenticate(request, username=uname, password=pword)
        if user is not None and user.is_active:
            login(request, user)
            write_audit_log(user, "LOGIN", "tblUsers", uname, "Successful web login")
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
            
    return render(request, 'registration/login.html')


@login_required
def logout_view(request):
    write_audit_log(request.user, "LOGOUT", "tblUsers", request.user.username, "User logged out")
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    today = date.today()
    ten_days_later = today + timedelta(days=10)

    # 1. Upcoming MDTs (next 10 days, status='Approved')
    upcoming_mdts = ClinicalDetails.objects.filter(
        date_mdt_planned__gte=today,
        date_mdt_planned__lte=ten_days_later,
        status='Approved'
    ).select_related('patient').order_by('date_mdt_planned')

    # 2. Recent Conducted MDTs (Approved consensus, top 10)
    recent_mdts = MDTConsensus.objects.filter(
        status='Approved'
    ).select_related('clinical_details', 'clinical_details__patient').order_by('-date_mdt_conducted')[:10]

    # Metrics
    stats = {
        'total_patients': Patient.objects.count(),
        'upcoming_count': upcoming_mdts.count(),
        'recent_count': recent_mdts.count(),
        'draft_clinicals': ClinicalDetails.objects.filter(status='Draft').count(),
        'pending_mdt': MDTConsensus.objects.filter(status='Draft').count(),
    }

    context = {
        'stats': stats,
        'upcoming_mdts': upcoming_mdts,
        'recent_mdts': recent_mdts,
        'today': today,
    }
    return render(request, 'mdt/dashboard.html', context)


# ==========================================
# Patient Registration & Search
# ==========================================

@login_required
def patient_search(request):
    query = request.GET.get('q', '').strip()
    selected_patient = None
    patient_history = []

    if query:
        # Search by exact or partial MR No, Name, or Phone
        patients = Patient.objects.filter(
            mr_no__icontains=query
        ) | Patient.objects.filter(
            name__icontains=query
        ) | Patient.objects.filter(
            phone__icontains=query
        )

        if patients.count() == 1:
            selected_patient = patients.first()
        elif patients.count() > 1:
            exact = Patient.objects.filter(mr_no__iexact=query).first()
            if exact:
                selected_patient = exact
            else:
                return render(request, 'mdt/patient_search.html', {
                    'query': query,
                    'patient_matches': patients[:15],
                })
        else:
            messages.warning(request, f"No patient found matching '{query}'.")

    mr = request.GET.get('mr', '').strip()
    if mr:
        selected_patient = Patient.objects.filter(mr_no=mr).first()

    if selected_patient:
        patient_history = ClinicalDetails.objects.filter(
            patient=selected_patient
        ).select_related('consensus').order_by('-clinical_id')

    context = {
        'query': query,
        'patient': selected_patient,
        'patient_history': patient_history,
        'primary_sites': PrimarySite.objects.all(),
    }
    return render(request, 'mdt/patient_search.html', context)


@login_required
def patient_create(request):
    if request.method == 'POST':
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save(commit=False)
            patient.is_locked = True
            patient.entered_by = request.user.username
            patient.save()
            write_audit_log(request.user, "REGISTER", "tblPtDetails", patient.mr_no, "New patient registered")
            messages.success(request, f"Patient {patient.name} ({patient.mr_no}) registered successfully.")
            return redirect(f"/patients/search/?mr={patient.mr_no}")
    else:
        form = PatientForm(initial={'country': 'India'})

    return render(request, 'mdt/patient_form.html', {
        'form': form,
        'is_new': True,
        'primary_sites': PrimarySite.objects.all(),
        'states': State.objects.all(),
    })


@login_required
def patient_edit(request, mr_no):
    patient = get_object_or_404(Patient, mr_no=mr_no)
    is_admin = hasattr(request.user, 'profile') and request.user.profile.role in ['Admin', 'SubAdmin']

    if patient.is_locked and not is_admin:
        messages.error(request, "This patient record is locked. Only an Administrator can unlock and edit demographics.")
        return redirect(f"/patients/search/?mr={patient.mr_no}")

    if request.method == 'POST':
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            p = form.save(commit=False)
            p.last_modified_by = request.user.username
            p.save()
            write_audit_log(request.user, "EDIT_PATIENT", "tblPtDetails", p.mr_no, "Admin modified patient record")
            messages.success(request, f"Patient record {p.mr_no} updated successfully.")
            return redirect(f"/patients/search/?mr={p.mr_no}")
    else:
        form = PatientForm(instance=patient)

    return render(request, 'mdt/patient_form.html', {
        'form': form,
        'patient': patient,
        'is_new': False,
        'primary_sites': PrimarySite.objects.all(),
        'states': State.objects.all(),
    })


def api_districts(request):
    state_id = request.GET.get('state_id')
    if not state_id:
        return JsonResponse({'districts': []})
    districts = District.objects.filter(state__state_id=state_id).values('district_id', 'district_name')
    return JsonResponse({'districts': list(districts)})


# ==========================================
# Clinical Presentation / Details
# ==========================================

@login_required
def clinical_create(request, mr_no):
    patient = get_object_or_404(Patient, mr_no=mr_no)

    if request.method == 'POST':
        form = ClinicalDetailsForm(request.POST)
        if form.is_valid():
            clinical = form.save(commit=False)
            clinical.patient = patient
            clinical.status = 'Draft'
            clinical.entered_by = request.user.username
            clinical.save()

            if clinical.diagnosis:
                cascade_diagnosis(patient.mr_no, clinical.diagnosis, request.user)

            write_audit_log(request.user, "SAVE_CLINICAL", "tblClinicalDetails", patient.mr_no, f"ClinicalID: {clinical.clinical_id}")
            messages.success(request, f"Clinical Presentation #{clinical.clinical_id} saved as Draft.")
            return redirect('clinical_edit', clinical_id=clinical.clinical_id)
    else:
        initial = {
            'diagnosis': patient.diagnosis,
            'date_mdt_planned': date.today() + timedelta(days=7),
            'discussion_category': 'Initial Staging',
        }
        form = ClinicalDetailsForm(initial=initial)

    return render(request, 'mdt/clinical_form.html', {
        'form': form,
        'patient': patient,
        'is_new': True,
    })


@login_required
def clinical_edit(request, clinical_id):
    clinical = get_object_or_404(ClinicalDetails.objects.select_related('patient', 'consensus'), clinical_id=clinical_id)
    patient = clinical.patient
    is_approved = clinical.status == 'Approved'

    if request.method == 'POST' and not is_approved:
        action = request.POST.get('action')

        if action == 'save_draft':
            form = ClinicalDetailsForm(request.POST, instance=clinical)
            if form.is_valid():
                c = form.save(commit=False)
                c.status = 'Draft'
                c.save()
                if c.diagnosis:
                    cascade_diagnosis(patient.mr_no, c.diagnosis, request.user)
                write_audit_log(request.user, "SAVE_CLINICAL", "tblClinicalDetails", patient.mr_no, f"ClinicalID: {c.clinical_id}")
                messages.success(request, "Clinical details saved as Draft.")
                return redirect('clinical_edit', clinical_id=clinical.clinical_id)

        elif action == 'approve':
            form = ClinicalDetailsForm(request.POST, instance=clinical)
            if form.is_valid():
                with transaction.atomic():
                    c = form.save(commit=False)
                    new_mdt_id = generate_next_mdt_id()
                    c.mdt_id = new_mdt_id
                    c.status = 'Approved'
                    c.approved_by = request.user.username
                    c.approved_on = timezone.now()
                    c.save()

                    # Create MDTConsensus stub if not exists
                    MDTConsensus.objects.get_or_create(
                        clinical_details=c,
                        defaults={
                            'mdt_id': new_mdt_id,
                            'date_mdt_conducted': c.date_mdt_planned or date.today(),
                            'status': 'Draft',
                            'entered_by': request.user.username,
                        }
                    )

                    if c.diagnosis:
                        cascade_diagnosis(patient.mr_no, c.diagnosis, request.user)

                    write_audit_log(request.user, "APPROVE_CLINICAL", "tblClinicalDetails", patient.mr_no, f"MDTID generated: {new_mdt_id}")
                    messages.success(request, f"Clinical details APPROVED! MDT ID generated: {new_mdt_id}")
                    return redirect('clinical_edit', clinical_id=clinical.clinical_id)
    else:
        form = ClinicalDetailsForm(instance=clinical)

    # Forms for investigations modal
    blood_form = BloodInvestigationForm(initial={'test_date': date.today()})
    imaging_form = ImagingInvestigationForm(initial={'imaging_date': date.today()})
    path_form = PathologyInvestigationForm(initial={'path_date': date.today()})
    mol_form = MolecularInvestigationForm(initial={'test_date': date.today()})

    context = {
        'form': form,
        'clinical': clinical,
        'patient': patient,
        'is_approved': is_approved,
        'blood_tests': clinical.blood_tests.all(),
        'imaging_tests': clinical.imaging_tests.all(),
        'pathology_tests': clinical.pathology_tests.all(),
        'molecular_tests': clinical.molecular_tests.all(),
        'blood_form': blood_form,
        'imaging_form': imaging_form,
        'path_form': path_form,
        'mol_form': mol_form,
    }
    return render(request, 'mdt/clinical_form.html', context)


# ==========================================
# Diagnostic Investigations Handlers
# ==========================================

@login_required
def investigation_add(request, clinical_id, inv_type):
    clinical = get_object_or_404(ClinicalDetails, clinical_id=clinical_id)
    if clinical.status == 'Approved':
        messages.error(request, "Cannot modify investigations for an Approved clinical record.")
        return redirect('clinical_edit', clinical_id=clinical_id)

    if request.method == 'POST':
        if inv_type == 'blood':
            f = BloodInvestigationForm(request.POST, request.FILES)
        elif inv_type == 'imaging':
            f = ImagingInvestigationForm(request.POST, request.FILES)
        elif inv_type == 'pathology':
            f = PathologyInvestigationForm(request.POST, request.FILES)
        elif inv_type == 'molecular':
            f = MolecularInvestigationForm(request.POST, request.FILES)
        else:
            return redirect('clinical_edit', clinical_id=clinical_id)

        if f.is_valid():
            inv = f.save(commit=False)
            inv.clinical_details = clinical
            inv.entered_by = request.user.username
            inv.save()
            write_audit_log(request.user, f"ADD_{inv_type.upper()}", f"tbl{inv_type.capitalize()}", clinical.patient.mr_no, f"Added to ClinicalID: {clinical_id}")
            messages.success(request, f"{inv_type.capitalize()} investigation recorded successfully.")
        else:
            messages.error(request, f"Error saving investigation: {f.errors}")

    return redirect('clinical_edit', clinical_id=clinical_id)


@login_required
def investigation_delete(request, inv_type, inv_id):
    if inv_type == 'blood':
        item = get_object_or_404(BloodInvestigation, id=inv_id)
    elif inv_type == 'imaging':
        item = get_object_or_404(ImagingInvestigation, id=inv_id)
    elif inv_type == 'pathology':
        item = get_object_or_404(PathologyInvestigation, id=inv_id)
    elif inv_type == 'molecular':
        item = get_object_or_404(MolecularInvestigation, id=inv_id)
    else:
        return redirect('dashboard')

    clinical_id = item.clinical_details.clinical_id
    if item.clinical_details.status == 'Approved':
        messages.error(request, "Cannot delete investigations from an Approved clinical record.")
        return redirect('clinical_edit', clinical_id=clinical_id)

    mr = item.clinical_details.patient.mr_no
    item.delete()
    write_audit_log(request.user, f"DELETE_{inv_type.upper()}", f"tbl{inv_type.capitalize()}", mr, f"Deleted ID: {inv_id}")
    messages.success(request, f"Investigation deleted successfully.")
    return redirect('clinical_edit', clinical_id=clinical_id)


# ==========================================
# MDT Consensus Discussion
# ==========================================

@login_required
def consensus_edit(request, consensus_id):
    consensus = get_object_or_404(
        MDTConsensus.objects.select_related('clinical_details', 'clinical_details__patient'),
        consensus_id=consensus_id
    )
    clinical = consensus.clinical_details
    patient = clinical.patient
    is_approved = consensus.status == 'Approved'

    if request.method == 'POST' and not is_approved:
        action = request.POST.get('action')

        if action == 'save_draft':
            form = MDTConsensusForm(request.POST, instance=consensus)
            if form.is_valid():
                c = form.save(commit=False)
                c.status = 'Draft'
                c.save()

                new_diag = request.POST.get('updated_diagnosis', '').strip()
                if new_diag and new_diag != clinical.diagnosis:
                    clinical.diagnosis = new_diag
                    clinical.save(update_fields=['diagnosis'])
                    cascade_diagnosis(patient.mr_no, new_diag, request.user)

                write_audit_log(request.user, "SAVE_MDT", "tblMDTConsensus", consensus.mdt_id or str(consensus.consensus_id), "MDT discussion saved as Draft")
                messages.success(request, "MDT discussion saved as Draft.")
                return redirect('consensus_edit', consensus_id=consensus.consensus_id)

        elif action == 'approve':
            form = MDTConsensusForm(request.POST, instance=consensus)
            if form.is_valid():
                with transaction.atomic():
                    c = form.save(commit=False)
                    c.status = 'Approved'
                    c.date_mdt_conducted = c.date_mdt_conducted or date.today()
                    c.approved_by = request.user.username
                    c.approved_on = timezone.now()
                    c.save()

                    new_diag = request.POST.get('updated_diagnosis', '').strip()
                    if new_diag and new_diag != clinical.diagnosis:
                        clinical.diagnosis = new_diag
                        clinical.save(update_fields=['diagnosis'])
                        cascade_diagnosis(patient.mr_no, new_diag, request.user)

                    write_audit_log(request.user, "APPROVE_MDT", "tblMDTConsensus", consensus.mdt_id or str(consensus.consensus_id), "MDT discussion APPROVED")
                    messages.success(request, "MDT Discussion APPROVED and finalized.")
                    return redirect('consensus_edit', consensus_id=consensus.consensus_id)
    else:
        form = MDTConsensusForm(instance=consensus)

    investigations = get_consolidated_investigations(clinical)
    doctors = UserProfile.objects.filter(role__in=['Consultant', 'Resident', 'Admin', 'SubAdmin']).select_related('user').order_by('full_name')

    context = {
        'form': form,
        'consensus': consensus,
        'clinical': clinical,
        'patient': patient,
        'is_approved': is_approved,
        'investigations': investigations,
        'doctors': doctors,
    }
    return render(request, 'mdt/consensus_form.html', context)


# ==========================================
# Live MDT Meeting Mode (Big Screen)
# ==========================================

@login_required
def live_presentation(request, consensus_id):
    consensus = get_object_or_404(
        MDTConsensus.objects.select_related('clinical_details', 'clinical_details__patient'),
        consensus_id=consensus_id
    )
    clinical = consensus.clinical_details
    patient = clinical.patient
    investigations = get_consolidated_investigations(clinical)

    if request.method == 'POST' and consensus.status != 'Approved':
        consensus.mdt_discussion = request.POST.get('mdt_discussion', '')
        consensus.consensus = request.POST.get('consensus', '')
        consensus.followup_actions = request.POST.get('followup_actions', '')
        consensus.attendees = request.POST.get('attendees', '')
        consensus.save()
        messages.success(request, "Real-time meeting notes updated.")
        return redirect('live_presentation', consensus_id=consensus.consensus_id)

    doctors = UserProfile.objects.filter(role__in=['Consultant', 'Resident', 'Admin', 'SubAdmin']).select_related('user').order_by('full_name')

    context = {
        'consensus': consensus,
        'clinical': clinical,
        'patient': patient,
        'investigations': investigations,
        'doctors': doctors,
    }
    return render(request, 'mdt/live_presentation.html', context)


# ==========================================
# Reports & Formal Printouts
# ==========================================

@login_required
def report_clinical_summary(request, clinical_id):
    clinical = get_object_or_404(
        ClinicalDetails.objects.select_related('patient'),
        clinical_id=clinical_id
    )
    patient = clinical.patient
    investigations = get_consolidated_investigations(clinical)
    write_audit_log(request.user, "PRINT_CLINICAL", "tblClinicalDetails", patient.mr_no, f"ClinicalID: {clinical_id}")

    context = {
        'clinical': clinical,
        'patient': patient,
        'investigations': investigations,
        'print_date': timezone.now(),
    }
    return render(request, 'mdt/report_clinical_summary.html', context)


@login_required
def report_mdt_full(request, consensus_id):
    consensus = get_object_or_404(
        MDTConsensus.objects.select_related('clinical_details', 'clinical_details__patient'),
        consensus_id=consensus_id
    )
    clinical = consensus.clinical_details
    patient = clinical.patient
    investigations = get_consolidated_investigations(clinical)
    write_audit_log(request.user, "PRINT", "tblMDTConsensus", consensus.mdt_id or str(consensus.consensus_id), f"Full MDT Report printed")

    context = {
        'consensus': consensus,
        'clinical': clinical,
        'patient': patient,
        'investigations': investigations,
        'print_date': timezone.now(),
    }
    return render(request, 'mdt/report_mdt_full.html', context)


# ==========================================
# Audit Trail & User Governance
# ==========================================

@login_required
def audit_log_view(request):
    is_admin = hasattr(request.user, 'profile') and request.user.profile.role in ['Admin', 'SubAdmin']
    if not is_admin and not request.user.is_superuser:
        return HttpResponseForbidden("Access Denied: Only Administrators can inspect audit logs.")

    query = request.GET.get('q', '').strip()
    logs = AuditLog.objects.all()
    if query:
        logs = logs.filter(
            username__icontains=query
        ) | logs.filter(
            action__icontains=query
        ) | logs.filter(
            record_ref__icontains=query
        ) | logs.filter(
            notes__icontains=query
        )

    logs = logs[:100]
    return render(request, 'mdt/audit_log.html', {'logs': logs, 'query': query})
