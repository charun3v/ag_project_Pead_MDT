import json
import csv
import io
import zipfile
from datetime import date, timedelta, datetime, time
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from .models import (
    Patient, ClinicalDetails, MDTConsensus, State, District, PrimarySite,
    BloodInvestigation, ImagingInvestigation, PathologyInvestigation, MolecularInvestigation,
    AuditLog, UserProfile, DiscussionPurpose, MDTPanelMember, Department, Designation
)
from .forms import (
    PatientForm, ClinicalDetailsForm, MDTConsensusForm,
    BloodInvestigationForm, ImagingInvestigationForm, PathologyInvestigationForm, MolecularInvestigationForm
)
from .services import (
    generate_next_mdt_id, write_audit_log, cascade_diagnosis, get_consolidated_investigations
)
from .lookup_config import LOOKUP_CONFIG, get_lookup_config


def is_admin_user(user):
    """Checks if user has Admin or SubAdmin privileges."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return hasattr(user, 'profile') and user.profile.role in ['Admin', 'SubAdmin']


def is_admin_only(user):
    """Checks if user has strict Administrator privileges (not SubAdmin)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return hasattr(user, 'profile') and user.profile.role == 'Admin'



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

    # 1. Upcoming MDTs (next 10 days, status in ['Scheduled', 'Approved'])
    upcoming_mdts = ClinicalDetails.objects.filter(
        date_mdt_planned__gte=today,
        date_mdt_planned__lte=ten_days_later,
        status__in=['Scheduled', 'Approved']
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
        initial_purpose = DiscussionPurpose.objects.filter(is_active=True).first()
        initial = {
            'diagnosis': patient.diagnosis,
            'date_mdt_planned': date.today() + timedelta(days=7),
            'discussion_purpose': initial_purpose,
        }
        form = ClinicalDetailsForm(initial=initial)

    discussion_purposes = DiscussionPurpose.objects.filter(is_active=True).order_by('display_order', 'name')

    return render(request, 'mdt/clinical_form.html', {
        'form': form,
        'patient': patient,
        'is_new': True,
        'discussion_purposes': discussion_purposes,
    })


@login_required
def clinical_edit(request, clinical_id):
    clinical = get_object_or_404(ClinicalDetails.objects.select_related('patient', 'consensus'), clinical_id=clinical_id)
    patient = clinical.patient
    lock_info = clinical.get_lock_status(request.user)
    is_editable = lock_info['can_edit']
    is_approved = clinical.is_approved

    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. Re-scheduling MDT: allowed for all authorized staff to unlock or reschedule
        if action == 'reschedule_mdt':
            new_date_str = request.POST.get('date_mdt_planned')
            if not new_date_str:
                messages.error(request, "Please provide a valid Planned MDT Date.")
                return redirect('clinical_edit', clinical_id=clinical.clinical_id)
            try:
                new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Invalid date format for Planned MDT Date.")
                return redirect('clinical_edit', clinical_id=clinical.clinical_id)

            with transaction.atomic():
                old_date = clinical.date_mdt_planned
                clinical.date_mdt_planned = new_date
                clinical.status = 'Scheduled'
                if not clinical.mdt_id:
                    clinical.mdt_id = generate_next_mdt_id()
                    clinical.approved_by = request.user.username
                    clinical.approved_on = timezone.now()
                clinical.save()

                consensus, _ = MDTConsensus.objects.get_or_create(
                    clinical_details=clinical,
                    defaults={
                        'mdt_id': clinical.mdt_id,
                        'date_mdt_conducted': new_date,
                        'status': 'Draft',
                        'entered_by': request.user.username,
                    }
                )
                if consensus:
                    consensus.date_mdt_conducted = new_date
                    consensus.save()

                write_audit_log(
                    request.user, "RESCHEDULE_MDT", "tblClinicalDetails", patient.mr_no,
                    f"Rescheduled Clinical #{clinical.clinical_id} from {old_date} to {new_date}"
                )
                messages.success(
                    request,
                    f"MDT successfully re-scheduled to {new_date.strftime('%d-%b-%Y')}. "
                    f"Clinical presentation is editable until 17:00 hrs on {new_date.strftime('%d-%b-%Y')}."
                )
                return redirect('clinical_edit', clinical_id=clinical.clinical_id)

        # 2. Block modifications if past 17:00 and user is non-admin
        elif not is_editable:
            messages.error(
                request,
                f"Record is locked (past 17:00 on scheduled date {clinical.date_mdt_planned}). "
                f"Only Administrators can edit directly. Click 'Re-schedule MDT' below to reopen editing."
            )
            return redirect('clinical_edit', clinical_id=clinical.clinical_id)

        # 3. Save Draft
        elif action == 'save_draft':
            form = ClinicalDetailsForm(request.POST, instance=clinical)
            if form.is_valid():
                c = form.save(commit=False)
                if c.status not in ['Scheduled', 'Approved']:
                    c.status = 'Draft'
                c.save()
                if c.diagnosis:
                    cascade_diagnosis(patient.mr_no, c.diagnosis, request.user)
                write_audit_log(request.user, "SAVE_CLINICAL", "tblClinicalDetails", patient.mr_no, f"ClinicalID: {c.clinical_id}")
                messages.success(request, "Clinical presentation saved as Draft.")
                return redirect('clinical_edit', clinical_id=clinical.clinical_id)

        # 4. Schedule MDT / Approve
        elif action in ['schedule_mdt', 'approve']:
            form = ClinicalDetailsForm(request.POST, instance=clinical)
            if form.is_valid():
                with transaction.atomic():
                    c = form.save(commit=False)
                    if not c.date_mdt_planned:
                        messages.error(request, "Please enter a Planned MDT Date before scheduling.")
                        return redirect('clinical_edit', clinical_id=clinical.clinical_id)

                    new_mdt_id = c.mdt_id or generate_next_mdt_id()
                    c.mdt_id = new_mdt_id
                    c.status = 'Scheduled' if action == 'schedule_mdt' else 'Approved'
                    c.approved_by = request.user.username
                    c.approved_on = timezone.now()
                    c.save()

                    # Create or sync MDTConsensus stub
                    consensus, _ = MDTConsensus.objects.get_or_create(
                        clinical_details=c,
                        defaults={
                            'mdt_id': new_mdt_id,
                            'date_mdt_conducted': c.date_mdt_planned or date.today(),
                            'status': 'Draft',
                            'entered_by': request.user.username,
                        }
                    )
                    if consensus and c.date_mdt_planned:
                        consensus.date_mdt_conducted = c.date_mdt_planned
                        consensus.save()

                    if c.diagnosis:
                        cascade_diagnosis(patient.mr_no, c.diagnosis, request.user)

                    action_name = "SCHEDULE_MDT" if action == 'schedule_mdt' else "APPROVE_CLINICAL"
                    write_audit_log(request.user, action_name, "tblClinicalDetails", patient.mr_no, f"MDTID generated: {new_mdt_id}")
                    messages.success(
                        request,
                        f"MDT successfully scheduled for {c.date_mdt_planned.strftime('%d-%b-%Y')}! MDT ID: {new_mdt_id}. "
                        f"Clinical details remain editable until 17:00 hrs on {c.date_mdt_planned.strftime('%d-%b-%Y')}."
                    )
                    return redirect('clinical_edit', clinical_id=clinical.clinical_id)
    else:
        form = ClinicalDetailsForm(instance=clinical)

    # Forms for investigations modal
    blood_form = BloodInvestigationForm(initial={'test_date': date.today()})
    imaging_form = ImagingInvestigationForm(initial={'imaging_date': date.today()})
    path_form = PathologyInvestigationForm(initial={'path_date': date.today()})
    mol_form = MolecularInvestigationForm(initial={'test_date': date.today()})

    all_investigations = get_consolidated_investigations(clinical)

    context = {
        'form': form,
        'clinical': clinical,
        'patient': patient,
        'lock_info': lock_info,
        'is_editable': is_editable,
        'is_locked': lock_info['is_locked'],
        'is_scheduled': lock_info['is_scheduled'],
        'is_admin': lock_info['is_admin'],
        'is_approved': is_approved,
        'blood_tests': clinical.blood_tests.all(),
        'imaging_tests': clinical.imaging_tests.all(),
        'pathology_tests': clinical.pathology_tests.all(),
        'molecular_tests': clinical.molecular_tests.all(),
        'all_investigations': all_investigations,
        'blood_form': blood_form,
        'imaging_form': imaging_form,
        'path_form': path_form,
        'mol_form': mol_form,
        'discussion_purposes': DiscussionPurpose.objects.filter(is_active=True).order_by('display_order', 'name'),
        'default_planned_date': (date.today() + timedelta(days=7)).strftime('%Y-%m-%d'),
    }
    return render(request, 'mdt/clinical_form.html', context)


@login_required
def clinical_reschedule(request, clinical_id):
    """
    Dedicated endpoint to re-schedule MDT date.
    Accessible from Patient Details / History page as well as Clinical Form.
    Updating the scheduled MDT date to today/future date reopens editing.
    """
    clinical = get_object_or_404(ClinicalDetails.objects.select_related('patient', 'consensus'), clinical_id=clinical_id)
    patient = clinical.patient
    next_url = request.POST.get('next_url') or request.GET.get('next') or (reverse('patient_search') + f"?mr={patient.mr_no}")

    if request.method == 'POST':
        new_date_str = request.POST.get('new_date') or request.POST.get('date_mdt_planned')
        if not new_date_str:
            messages.error(request, "Please provide a valid Planned MDT Date.")
            return redirect(next_url)
        try:
            new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect(next_url)

        with transaction.atomic():
            old_date = clinical.date_mdt_planned
            clinical.date_mdt_planned = new_date
            clinical.status = 'Scheduled'
            if not clinical.mdt_id:
                clinical.mdt_id = generate_next_mdt_id()
                clinical.approved_by = request.user.username
                clinical.approved_on = timezone.now()
            clinical.save()

            consensus, _ = MDTConsensus.objects.get_or_create(
                clinical_details=clinical,
                defaults={
                    'mdt_id': clinical.mdt_id,
                    'date_mdt_conducted': new_date,
                    'status': 'Draft',
                    'entered_by': request.user.username,
                }
            )
            if consensus:
                consensus.date_mdt_conducted = new_date
                consensus.save()

            write_audit_log(
                request.user, "RESCHEDULE_MDT", "tblClinicalDetails", patient.mr_no,
                f"Rescheduled MDT #{clinical.clinical_id} from {old_date} to {new_date}"
            )
            messages.success(
                request,
                f"MDT #{clinical.clinical_id} successfully re-scheduled to {new_date.strftime('%d-%b-%Y')}. "
                f"Clinical presentation is now editable until 17:00 hrs on {new_date.strftime('%d-%b-%Y')}."
            )
            return redirect(next_url)

    return redirect(next_url)


# ==========================================
# Diagnostic Investigations Handlers
# ==========================================

@login_required
def investigation_add(request, clinical_id, inv_type):
    clinical = get_object_or_404(ClinicalDetails, clinical_id=clinical_id)
    lock_info = clinical.get_lock_status(request.user)
    if not lock_info['can_edit']:
        messages.error(
            request,
            f"Cannot modify investigations: Clinical presentation is locked (past 17:00 on {clinical.date_mdt_planned}). "
            f"Re-schedule MDT to make edits."
        )
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

    clinical = item.clinical_details
    clinical_id = clinical.clinical_id
    lock_info = clinical.get_lock_status(request.user)
    if not lock_info['can_edit']:
        messages.error(
            request,
            f"Cannot delete investigations: Clinical presentation is locked (past 17:00 on {clinical.date_mdt_planned}). "
            f"Re-schedule MDT to make edits."
        )
        return redirect('clinical_edit', clinical_id=clinical_id)

    mr = clinical.patient.mr_no
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
    quick_add_users = UserProfile.objects.filter(
        in_quick_add_panel=True,
        user__is_active=True
    ).select_related('user', 'department', 'designation').order_by('full_name', 'user__username')
    doctors = UserProfile.objects.filter(
        user__is_active=True
    ).select_related('user', 'department', 'designation').order_by('full_name', 'user__username')
    panel_members = MDTPanelMember.objects.filter(is_active=True).order_by('display_order', 'name')

    context = {
        'form': form,
        'consensus': consensus,
        'clinical': clinical,
        'patient': patient,
        'is_approved': is_approved,
        'investigations': investigations,
        'doctors': doctors,
        'quick_add_users': quick_add_users,
        'panel_members': panel_members,
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

    quick_add_users = UserProfile.objects.filter(
        in_quick_add_panel=True,
        user__is_active=True
    ).select_related('user', 'department', 'designation').order_by('full_name', 'user__username')
    doctors = UserProfile.objects.filter(
        user__is_active=True
    ).select_related('user', 'department', 'designation').order_by('full_name', 'user__username')
    panel_members = MDTPanelMember.objects.filter(is_active=True).order_by('display_order', 'name')

    context = {
        'consensus': consensus,
        'clinical': clinical,
        'patient': patient,
        'investigations': investigations,
        'doctors': doctors,
        'quick_add_users': quick_add_users,
        'panel_members': panel_members,
    }
    return render(request, 'mdt/live_presentation.html', context)


@login_required
def api_add_panel_member(request):
    """
    API / endpoint to add a custom panel member name to MDTPanelMember lookup.
    """
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        specialty = request.POST.get('specialty', '').strip()
        if not name:
            return JsonResponse({'success': False, 'error': 'Name is required.'}, status=400)
        
        member, created = MDTPanelMember.objects.get_or_create(
            name=name,
            defaults={
                'specialty': specialty,
                'is_active': True,
                'display_order': MDTPanelMember.objects.count() + 1
            }
        )
        return JsonResponse({
            'success': True,
            'created': created,
            'id': member.id,
            'name': member.name,
            'specialty': member.specialty,
            'display': str(member)
        })
    return JsonResponse({'success': False, 'error': 'POST method required.'}, status=405)


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


# ==========================================
# Reference Lookups Management (Admin / SubAdmin)
# ==========================================

@login_required
def manage_purposes_view(request):
    if not is_admin_user(request.user):
        messages.error(request, "Access restricted to Administrators.")
        return redirect('dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()
            order_raw = request.POST.get('display_order', '').strip()
            if name:
                order_val = int(order_raw) if order_raw.isdigit() else (DiscussionPurpose.objects.count() + 1)
                obj, created = DiscussionPurpose.objects.get_or_create(
                    name=name,
                    defaults={'display_order': order_val, 'is_active': True}
                )
                if not created and not obj.is_active:
                    obj.is_active = True
                    obj.save()
                write_audit_log(
                    request.user,
                    "ADD_PURPOSE",
                    "tblDiscussionPurpose",
                    name,
                    f"Admin {request.user.username} created discussion purpose '{name}'."
                )
                messages.success(request, f"Discussion Purpose '{name}' added successfully.")
            else:
                messages.error(request, "Discussion purpose name cannot be empty.")

        elif action == 'toggle':
            purpose_id = request.POST.get('purpose_id')
            p = get_object_or_404(DiscussionPurpose, purpose_id=purpose_id)
            p.is_active = not p.is_active
            p.save()
            status_text = "activated" if p.is_active else "deactivated"
            write_audit_log(
                request.user,
                "TOGGLE_PURPOSE",
                "tblDiscussionPurpose",
                p.name,
                f"Admin {request.user.username} {status_text} purpose '{p.name}'."
            )
            messages.success(request, f"Purpose '{p.name}' has been {status_text}.")

        elif action == 'delete':
            if is_admin_only(request.user):
                purpose_id = request.POST.get('purpose_id')
                p = get_object_or_404(DiscussionPurpose, purpose_id=purpose_id)
                p_name = p.name
                p.delete()
                write_audit_log(
                    request.user,
                    "DELETE_PURPOSE",
                    "tblDiscussionPurpose",
                    p_name,
                    f"Admin {request.user.username} deleted purpose '{p_name}'."
                )
                messages.success(request, f"Purpose '{p_name}' permanently deleted.")
            else:
                messages.error(request, "Only Administrators can delete lookup entries.")

        return redirect('manage_purposes')

    purposes = DiscussionPurpose.objects.all().order_by('display_order', 'name')
    return render(request, 'mdt/manage_purposes.html', {'purposes': purposes})


@login_required
def api_add_discussion_purpose(request):
    if not is_admin_user(request.user):
        return JsonResponse({'error': 'Access denied: Administrators only'}, status=403)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Purpose name cannot be empty'}, status=400)

        obj, created = DiscussionPurpose.objects.get_or_create(
            name=name,
            defaults={'display_order': DiscussionPurpose.objects.count() + 1, 'is_active': True}
        )
        if not obj.is_active:
            obj.is_active = True
            obj.save()

        write_audit_log(
            request.user,
            "ADD_LOOKUP",
            "tblDiscussionPurpose",
            name,
            f"Admin {request.user.username} added MDT discussion purpose '{name}'."
        )
        return JsonResponse({'id': obj.purpose_id, 'name': obj.name, 'created': created})

    return JsonResponse({'error': 'POST method required'}, status=405)


@login_required
def api_reorder_discussion_purposes(request):
    if not is_admin_user(request.user):
        return JsonResponse({'error': 'Access denied: Administrators only'}, status=403)

    if request.method == 'POST':
        order_ids = []
        try:
            if request.body:
                data = json.loads(request.body)
                order_ids = data.get('order', [])
        except Exception:
            pass

        if not order_ids:
            order_ids = request.POST.getlist('order') or request.POST.getlist('order[]')

        if not order_ids:
            return JsonResponse({'error': 'No order sequence provided'}, status=400)

        with transaction.atomic():
            for idx, pid in enumerate(order_ids, start=1):
                try:
                    DiscussionPurpose.objects.filter(purpose_id=int(pid)).update(display_order=idx)
                except (ValueError, TypeError):
                    continue

        write_audit_log(
            request.user,
            "REORDER_PURPOSES",
            "tblDiscussionPurpose",
            f"{len(order_ids)} items",
            f"Admin {request.user.username} reordered discussion purposes via drag-and-drop."
        )
        return JsonResponse({'status': 'ok', 'message': 'Discussion purposes order updated successfully.'})

    return JsonResponse({'error': 'POST method required'}, status=405)




# ==========================================
# User Account Management (Admin / SubAdmin)
# ==========================================

@login_required
def user_list_view(request):
    if not is_admin_user(request.user):
        messages.error(request, "Access restricted to Administrators.")
        return redirect('dashboard')

    query = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()
    dept_filter = request.GET.get('department', '').strip()
    status_filter = request.GET.get('status', '').strip()
    quick_add_filter = request.GET.get('quick_add', '').strip()

    users_qs = User.objects.select_related('profile', 'profile__department', 'profile__designation').order_by('username')

    if query:
        users_qs = users_qs.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(profile__full_name__icontains=query) |
            Q(profile__department__name__icontains=query) |
            Q(profile__designation__name__icontains=query)
        )

    if role_filter:
        users_qs = users_qs.filter(profile__role=role_filter)

    if dept_filter:
        users_qs = users_qs.filter(profile__department_id=dept_filter)

    if quick_add_filter == '1':
        users_qs = users_qs.filter(profile__in_quick_add_panel=True)
    elif quick_add_filter == '0':
        users_qs = users_qs.filter(profile__in_quick_add_panel=False)

    if status_filter == 'active':
        users_qs = users_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        users_qs = users_qs.filter(is_active=False)

    total_count = users_qs.count()
    active_count = User.objects.filter(is_active=True).count()
    inactive_count = User.objects.filter(is_active=False).count()
    departments = Department.objects.filter(is_active=True)

    context = {
        'users': users_qs,
        'roles': UserProfile.ROLE_CHOICES,
        'departments': departments,
        'query': query,
        'selected_role': role_filter,
        'selected_dept': dept_filter,
        'quick_add_filter': quick_add_filter,
        'status_filter': status_filter,
        'is_admin': is_admin_only(request.user),
        'total_count': total_count,
        'active_count': active_count,
        'inactive_count': inactive_count,
    }
    return render(request, 'mdt/user_list.html', context)


@login_required
def user_create_view(request):
    if not is_admin_user(request.user):
        messages.error(request, "Access restricted to Administrators.")
        return redirect('dashboard')

    roles = UserProfile.ROLE_CHOICES
    prefixes = ['Dr.', 'Mr', 'Mrs', 'Ms', 'Prof.']
    departments = Department.objects.filter(is_active=True)
    designations = Designation.objects.filter(is_active=True)

    if request.method == 'POST':
        uname = request.POST.get('username', '').strip().lower()
        prefix = request.POST.get('prefix', 'Dr.').strip()
        fname = request.POST.get('first_name', '').strip()
        email = request.POST.get('email', '').strip()
        pword = request.POST.get('password', '').strip()
        role = request.POST.get('role', 'Consultant').strip()
        dept_id = request.POST.get('department', '').strip()
        desig_id = request.POST.get('designation', '').strip()
        in_quick_add = (request.POST.get('in_quick_add_panel') == 'on')

        if not uname or not pword:
            messages.error(request, "Username and Password are required.")
            return render(request, 'mdt/user_form.html', {
                'roles': roles, 'prefixes': prefixes,
                'departments': departments, 'designations': designations
            })

        if User.objects.filter(username__iexact=uname).exists():
            messages.error(request, f"Username '{uname}' already exists. Please choose a different username.")
            return render(request, 'mdt/user_form.html', {
                'roles': roles, 'prefixes': prefixes,
                'departments': departments, 'designations': designations
            })

        is_staff = role in ['Admin', 'SubAdmin']
        is_superuser = (role == 'Admin')

        user = User.objects.create_user(
            username=uname,
            email=email,
            password=pword,
            first_name=fname,
            is_staff=is_staff,
            is_superuser=is_superuser
        )

        dept_obj = Department.objects.filter(id=dept_id).first() if dept_id else None
        desig_obj = Designation.objects.filter(id=desig_id).first() if desig_id else None

        UserProfile.objects.update_or_create(
            user=user,
            defaults={
                'prefix': prefix,
                'full_name': fname,
                'role': role,
                'user_level': role.upper(),
                'department': dept_obj,
                'designation': desig_obj,
                'in_quick_add_panel': in_quick_add,
            }
        )

        write_audit_log(
            request.user,
            "USER_CREATE",
            "tblUsers",
            uname,
            f"Created user account '{uname}' ({prefix} {fname}) with role '{role}', dept '{dept_obj}', desig '{desig_obj}'."
        )

        messages.success(request, f"User account '{prefix} {fname or uname}' created successfully with role '{role}'.")
        return redirect('user_list')

    return render(request, 'mdt/user_form.html', {
        'roles': roles, 'prefixes': prefixes,
        'departments': departments, 'designations': designations,
        'target_user': None
    })


@login_required
def user_edit_view(request, user_id):
    if not is_admin_user(request.user):
        messages.error(request, "Access restricted to Administrators.")
        return redirect('dashboard')

    target_user = get_object_or_404(User.objects.select_related('profile'), id=user_id)
    roles = UserProfile.ROLE_CHOICES
    prefixes = ['Dr.', 'Mr', 'Mrs', 'Ms', 'Prof.']
    departments = Department.objects.filter(is_active=True)
    designations = Designation.objects.filter(is_active=True)
    is_admin = is_admin_only(request.user)

    if request.method == 'POST':
        prefix = request.POST.get('prefix', 'Dr.').strip()
        fname = request.POST.get('first_name', '').strip()
        email = request.POST.get('email', '').strip()
        role = request.POST.get('role', 'Consultant').strip()
        dept_id = request.POST.get('department', '').strip()
        desig_id = request.POST.get('designation', '').strip()
        in_quick_add = (request.POST.get('in_quick_add_panel') == 'on')
        new_pwd = request.POST.get('password', '').strip()

        target_user.first_name = fname
        target_user.email = email

        if is_admin and target_user.id != request.user.id:
            target_user.is_active = (request.POST.get('is_active') == 'on')

        if new_pwd:
            target_user.set_password(new_pwd)

        target_user.is_staff = role in ['Admin', 'SubAdmin']
        if role == 'Admin':
            target_user.is_superuser = True
        elif target_user.is_superuser and role != 'Admin' and target_user.id != request.user.id:
            target_user.is_superuser = False

        target_user.save()

        dept_obj = Department.objects.filter(id=dept_id).first() if dept_id else None
        desig_obj = Designation.objects.filter(id=desig_id).first() if desig_id else None

        profile, _ = UserProfile.objects.get_or_create(user=target_user)
        profile.prefix = prefix
        profile.full_name = fname
        profile.role = role
        profile.user_level = role.upper()
        profile.department = dept_obj
        profile.designation = desig_obj
        profile.in_quick_add_panel = in_quick_add
        profile.save()

        write_audit_log(
            request.user,
            "USER_EDIT",
            "tblUsers",
            target_user.username,
            f"Updated user account '{target_user.username}' (Name: {prefix} {fname}, Role: {role}, Dept: {dept_obj}, Desig: {desig_obj}, Active: {target_user.is_active})."
        )

        messages.success(request, f"User account '{target_user.username}' updated successfully.")
        return redirect('user_list')

    return render(request, 'mdt/user_form.html', {
        'target_user': target_user,
        'roles': roles,
        'prefixes': prefixes,
        'departments': departments,
        'designations': designations,
        'is_admin': is_admin,
    })


@login_required
def user_toggle_quick_add_view(request, user_id):
    if not is_admin_user(request.user):
        messages.error(request, "Access restricted to Administrators.")
        return redirect('user_list')

    target_user = get_object_or_404(User.objects.select_related('profile'), id=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    profile.in_quick_add_panel = not profile.in_quick_add_panel
    profile.save()

    status_str = "added to" if profile.in_quick_add_panel else "removed from"
    messages.success(request, f"User '{profile.get_display_name()}' has been {status_str} the MDT Quick-Add panel.")
    
    ref = request.META.get('HTTP_REFERER')
    if ref:
        return redirect(ref)
    return redirect('user_list')


@login_required
def user_toggle_active_view(request, user_id):
    if not is_admin_only(request.user):
        messages.error(request, "Access denied. Only Administrators can activate or deactivate accounts.")
        return redirect('user_list')

    target_user = get_object_or_404(User, id=user_id)
    if target_user.id == request.user.id:
        messages.error(request, "You cannot deactivate your own administrative account.")
        return redirect('user_list')

    target_user.is_active = not target_user.is_active
    target_user.save()

    status_str = "activated" if target_user.is_active else "deactivated"
    write_audit_log(
        request.user,
        f"USER_{status_str.upper()}",
        "tblUsers",
        target_user.username,
        f"Admin {request.user.username} {status_str} account for '{target_user.username}'."
    )

    messages.success(request, f"User '{target_user.username}' has been successfully {status_str}.")
    return redirect('user_list')


@login_required
def user_delete_view(request, user_id):
    if not is_admin_only(request.user):
        messages.error(request, "Access denied. Only Administrators can delete user accounts.")
        return redirect('user_list')

    target_user = get_object_or_404(User, id=user_id)
    if target_user.id == request.user.id:
        messages.error(request, "Action blocked: You cannot delete your own administrative account.")
        return redirect('user_list')

    if request.method == 'POST':
        confirm = request.POST.get('confirm_delete')
        if not confirm:
            messages.error(request, "Please check the confirmation box to verify permanent user deletion.")
            return render(request, 'mdt/user_confirm_delete.html', {'target_user': target_user})

        uname = target_user.username
        full_name = getattr(target_user.profile, 'full_name', '') or target_user.get_full_name() or uname
        role_name = getattr(target_user.profile, 'role', 'User')

        target_user.delete()

        write_audit_log(
            request.user,
            "USER_DELETE",
            "tblUsers",
            uname,
            f"Admin {request.user.username} permanently deleted user account '{uname}' ({full_name}, Role: {role_name})."
        )

        messages.success(request, f"User account '{uname}' has been permanently deleted.")
        return redirect('user_list')

    return render(request, 'mdt/user_confirm_delete.html', {'target_user': target_user})


# ==========================================
# Admin Record Deletion Views
# ==========================================

@login_required
def patient_delete_view(request, mr_no):
    if not is_admin_user(request.user):
        messages.error(request, "Access restricted. Only Administrators can delete patient records.")
        return redirect('patient_search')

    patient = get_object_or_404(Patient, mr_no__iexact=mr_no)
    episodes = patient.clinical_episodes.all()
    episodes_count = episodes.count()
    consensus_count = MDTConsensus.objects.filter(clinical_details__in=episodes).count()
    blood_count = BloodInvestigation.objects.filter(clinical_details__in=episodes).count()
    imaging_count = ImagingInvestigation.objects.filter(clinical_details__in=episodes).count()
    pathology_count = PathologyInvestigation.objects.filter(clinical_details__in=episodes).count()
    molecular_count = MolecularInvestigation.objects.filter(clinical_details__in=episodes).count()
    total_inv_count = blood_count + imaging_count + pathology_count + molecular_count

    if request.method == 'POST':
        confirm = request.POST.get('confirm_delete')
        if not confirm:
            messages.error(request, "You must check the confirmation checkbox to delete this patient.")
            return render(request, 'mdt/patient_confirm_delete.html', {
                'patient': patient,
                'episodes_count': episodes_count,
                'consensus_count': consensus_count,
                'total_inv_count': total_inv_count,
                'blood_count': blood_count,
                'imaging_count': imaging_count,
                'pathology_count': pathology_count,
                'molecular_count': molecular_count,
            })

        with transaction.atomic():
            p_mr = patient.mr_no
            p_name = patient.name
            patient.delete()

            write_audit_log(
                request.user,
                "DELETE_PATIENT",
                "tblPatients",
                p_mr,
                f"Permanently deleted patient {p_mr} ({p_name}) and all associated records: {episodes_count} MDTs, {consensus_count} consensus decisions, and {total_inv_count} investigations."
            )

        messages.success(request, f"Patient {p_mr} ({p_name}) and all associated records were permanently deleted.")
        return redirect('patient_search')

    return render(request, 'mdt/patient_confirm_delete.html', {
        'patient': patient,
        'episodes_count': episodes_count,
        'consensus_count': consensus_count,
        'total_inv_count': total_inv_count,
        'blood_count': blood_count,
        'imaging_count': imaging_count,
        'pathology_count': pathology_count,
        'molecular_count': molecular_count,
    })


@login_required
def clinical_delete_view(request, clinical_id):
    if not is_admin_user(request.user):
        messages.error(request, "Access restricted. Only Administrators can delete MDT presentations.")
        return redirect('dashboard')

    clinical = get_object_or_404(ClinicalDetails, clinical_id=clinical_id)
    patient = clinical.patient
    has_consensus = hasattr(clinical, 'consensus') and clinical.consensus is not None
    blood_count = clinical.blood_tests.count()
    imaging_count = clinical.imaging_tests.count()
    pathology_count = clinical.pathology_tests.count()
    molecular_count = clinical.molecular_tests.count()
    total_inv_count = blood_count + imaging_count + pathology_count + molecular_count

    if request.method == 'POST':
        confirm = request.POST.get('confirm_delete')
        if not confirm:
            messages.error(request, "You must check the confirmation checkbox to delete this presentation.")
            return render(request, 'mdt/clinical_confirm_delete.html', {
                'clinical': clinical,
                'patient': patient,
                'has_consensus': has_consensus,
                'total_inv_count': total_inv_count,
                'blood_count': blood_count,
                'imaging_count': imaging_count,
                'pathology_count': pathology_count,
                'molecular_count': molecular_count,
            })

        with transaction.atomic():
            mdt_ref = f"Clinical #{clinical.clinical_id} (MDT ID: {clinical.mdt_id or 'Draft'})"
            p_mr = patient.mr_no
            p_name = patient.name
            clinical.delete()

            write_audit_log(
                request.user,
                "DELETE_MDT",
                "tblClinicalDetails",
                mdt_ref,
                f"Permanently deleted MDT presentation {mdt_ref} for patient {p_mr} ({p_name}) including attached consensus and {total_inv_count} investigations."
            )

        messages.success(request, f"MDT Presentation {mdt_ref} for patient {p_name} has been permanently deleted.")
        return redirect(f"/patients/search/?q={p_mr}")

    return render(request, 'mdt/clinical_confirm_delete.html', {
        'clinical': clinical,
        'patient': patient,
        'has_consensus': has_consensus,
        'total_inv_count': total_inv_count,
        'blood_count': blood_count,
        'imaging_count': imaging_count,
        'pathology_count': pathology_count,
        'molecular_count': molecular_count,
    })


# ==========================================
# Data Export Views (Admin / SubAdmin)
# ==========================================

@login_required
def export_hub_view(request):
    if not is_admin_user(request.user):
        messages.error(request, "Access restricted to Administrators.")
        return redirect('dashboard')

    patient_count = Patient.objects.count()
    clinical_count = ClinicalDetails.objects.count()
    consensus_count = MDTConsensus.objects.count()
    inv_count = (
        BloodInvestigation.objects.count() +
        ImagingInvestigation.objects.count() +
        PathologyInvestigation.objects.count() +
        MolecularInvestigation.objects.count()
    )
    audit_count = AuditLog.objects.count()

    context = {
        'patient_count': patient_count,
        'clinical_count': clinical_count,
        'consensus_count': consensus_count,
        'inv_count': inv_count,
        'audit_count': audit_count,
    }
    return render(request, 'mdt/export_hub.html', context)


def generate_patients_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'MR No', 'Full Name', 'Sex', 'Date of Birth', 'Age (Paediatric Format)',
        'Primary Diagnosis', 'Primary Treatment Site', 'Laterality',
        'Primary Phone', 'Alternate Phone', 'Address', 'District', 'State',
        'PIN Code', 'Digipin', 'Clinical Notes', 'Registration Date'
    ])
    for p in Patient.objects.select_related('state', 'district').order_by('mr_no'):
        writer.writerow([
            p.mr_no,
            p.name,
            p.get_sex_display(),
            p.date_of_birth.strftime('%Y-%m-%d') if p.date_of_birth else '',
            p.format_age(),
            p.diagnosis or '',
            p.primary_treatment_site or '',
            p.laterality or '',
            p.phone or '',
            p.phone_alternate or '',
            p.address or '',
            p.district.district_name if p.district else '',
            p.state.state_name if p.state else '',
            p.pincode or '',
            p.digipin or '',
            p.notes or '',
            p.entered_on.strftime('%Y-%m-%d %H:%M') if p.entered_on else ''
        ])
    return output.getvalue()


def generate_mdt_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Clinical ID', 'MDT ID', 'MR No', 'Patient Name', 'Planned MDT Date',
        'Date MDT Conducted', 'Episode Status', 'Consensus Status', 'Height (cm)',
        'Weight (kg)', 'BSA (m2)', 'BMI (kg/m2)', 'Stage / Risk', 'Diagnosis',
        'Previous Treatment History', 'Discussion Category', 'Reason for Presentation',
        'Presenting Complaints', 'Examination Findings', 'MDT Attendees',
        'Discussion Points', 'Consensus Decision', 'Follow-up Actions', 'Entered By'
    ])
    for c in ClinicalDetails.objects.select_related('patient', 'consensus').order_by('-clinical_id'):
        cons = getattr(c, 'consensus', None)
        writer.writerow([
            c.clinical_id,
            c.mdt_id or '',
            c.patient.mr_no,
            c.patient.name,
            c.date_mdt_planned.strftime('%Y-%m-%d') if c.date_mdt_planned else '',
            cons.date_mdt_conducted.strftime('%Y-%m-%d') if (cons and cons.date_mdt_conducted) else '',
            c.status,
            cons.status if cons else 'No Consensus',
            c.height or '',
            c.weight or '',
            f"{c.bsa:.2f}" if c.bsa else '',
            f"{c.bmi:.2f}" if c.bmi else '',
            c.stage or '',
            c.diagnosis or '',
            c.prev_tx_history or '',
            c.discussion_purpose_display or '',
            c.mdt_discussion_for or '',
            c.presenting_complaints or '',
            c.examination_findings or '',
            cons.attendees if cons else '',
            cons.mdt_discussion if cons else '',
            cons.consensus if cons else '',
            cons.followup_actions if cons else '',
            c.entered_by or ''
        ])
    return output.getvalue()


def generate_investigations_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Investigation Type', 'Date', 'MR No', 'Patient Name', 'Clinical ID',
        'MDT ID', 'Modality / Specimen / Test Type', 'Site / Lab Ref No',
        'Details & Findings', 'Impression / Conclusion', 'Linked to MDT', 'Entered By', 'Entered Date'
    ])
    for b in BloodInvestigation.objects.select_related('clinical_details__patient', 'specimen_type').order_by('-test_date'):
        c = b.clinical_details
        writer.writerow([
            'Blood Investigation',
            b.test_date.strftime('%Y-%m-%d') if b.test_date else '',
            c.patient.mr_no,
            c.patient.name,
            c.clinical_id,
            c.mdt_id or '',
            b.specimen_type.specimen_type if b.specimen_type else '',
            '',
            b.details,
            b.impression or '',
            'Yes' if b.linked_to_mdt else 'No',
            b.entered_by or '',
            b.entered_on.strftime('%Y-%m-%d %H:%M') if b.entered_on else ''
        ])
    for img in ImagingInvestigation.objects.select_related('clinical_details__patient', 'imaging_type', 'site').order_by('-imaging_date'):
        c = img.clinical_details
        writer.writerow([
            'Imaging Investigation',
            img.imaging_date.strftime('%Y-%m-%d') if img.imaging_date else '',
            c.patient.mr_no,
            c.patient.name,
            c.clinical_id,
            c.mdt_id or '',
            img.imaging_type.type_name if img.imaging_type else '',
            img.site.site_name if img.site else '',
            img.details,
            img.impression or '',
            'Yes' if img.linked_to_mdt else 'No',
            img.entered_by or '',
            img.entered_on.strftime('%Y-%m-%d %H:%M') if img.entered_on else ''
        ])
    for p in PathologyInvestigation.objects.select_related('clinical_details__patient', 'specimen_type').order_by('-path_date'):
        c = p.clinical_details
        writer.writerow([
            'Pathology Investigation',
            p.path_date.strftime('%Y-%m-%d') if p.path_date else '',
            c.patient.mr_no,
            c.patient.name,
            c.clinical_id,
            c.mdt_id or '',
            p.specimen_type.specimen_name if p.specimen_type else '',
            f"{p.site_of_biopsy or ''} (Ref: {p.lab_reference_no or ''})".strip(),
            p.details,
            p.impression or '',
            'Yes' if p.linked_to_mdt else 'No',
            p.entered_by or '',
            p.entered_on.strftime('%Y-%m-%d %H:%M') if p.entered_on else ''
        ])
    for m in MolecularInvestigation.objects.select_related('clinical_details__patient', 'test_type').order_by('-test_date'):
        c = m.clinical_details
        writer.writerow([
            'Molecular Investigation',
            m.test_date.strftime('%Y-%m-%d') if m.test_date else '',
            c.patient.mr_no,
            c.patient.name,
            c.clinical_id,
            c.mdt_id or '',
            m.test_type.test_name if m.test_type else '',
            m.lab_reference_no or '',
            m.details,
            m.impression or '',
            'Yes' if m.linked_to_mdt else 'No',
            m.entered_by or '',
            m.entered_on.strftime('%Y-%m-%d %H:%M') if m.entered_on else ''
        ])
    return output.getvalue()


def generate_audit_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Log ID', 'Timestamp', 'Username', 'Staff Full Name', 'Action', 'Table Affected', 'Record Ref', 'Notes'])
    for log in AuditLog.objects.all().order_by('-timestamp'):
        writer.writerow([
            log.log_id,
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.username,
            log.full_name or '',
            log.action,
            log.table_affected,
            log.record_ref,
            log.notes or ''
        ])
    return output.getvalue()


@login_required
def export_patients_csv_view(request):
    if not is_admin_user(request.user):
        return HttpResponseForbidden("Access Denied.")
    csv_data = generate_patients_csv()
    filename = f"pead_mdt_patients_{date.today().strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    response.write(csv_data)
    write_audit_log(request.user, "EXPORT_DATA", "tblPatients", filename, "Exported patients register CSV")
    return response


@login_required
def export_mdt_csv_view(request):
    if not is_admin_user(request.user):
        return HttpResponseForbidden("Access Denied.")
    csv_data = generate_mdt_csv()
    filename = f"pead_mdt_presentations_{date.today().strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    response.write(csv_data)
    write_audit_log(request.user, "EXPORT_DATA", "tblClinicalDetails", filename, "Exported MDT presentations CSV")
    return response


@login_required
def export_investigations_csv_view(request):
    if not is_admin_user(request.user):
        return HttpResponseForbidden("Access Denied.")
    csv_data = generate_investigations_csv()
    filename = f"pead_mdt_investigations_{date.today().strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    response.write(csv_data)
    write_audit_log(request.user, "EXPORT_DATA", "tblInvestigations", filename, "Exported multi-modality investigations CSV")
    return response


@login_required
def export_audit_logs_csv_view(request):
    if not is_admin_user(request.user):
        return HttpResponseForbidden("Access Denied.")
    csv_data = generate_audit_csv()
    filename = f"pead_mdt_audit_log_{date.today().strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    response.write(csv_data)
    write_audit_log(request.user, "EXPORT_DATA", "AuditLog", filename, "Exported security audit log CSV")
    return response


@login_required
def export_all_zip_view(request):
    if not is_admin_user(request.user):
        return HttpResponseForbidden("Access Denied.")
    zip_buffer = io.BytesIO()
    datestr = date.today().strftime('%Y%m%d')
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(f"pead_mdt_patients_{datestr}.csv", '\ufeff' + generate_patients_csv())
        zip_file.writestr(f"pead_mdt_presentations_{datestr}.csv", '\ufeff' + generate_mdt_csv())
        zip_file.writestr(f"pead_mdt_investigations_{datestr}.csv", '\ufeff' + generate_investigations_csv())
        zip_file.writestr(f"pead_mdt_audit_log_{datestr}.csv", '\ufeff' + generate_audit_csv())

    filename = f"pead_mdt_complete_export_{datestr}.zip"
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    write_audit_log(request.user, "EXPORT_DATA", "ALL_TABLES", filename, "Exported complete database ZIP archive")
    return response


# ==========================================
# Scheduler-Style Centralized Dropdown & Lookup Tables Manager (Admin / SubAdmin)
# ==========================================

@login_required
def lookup_manager_view(request, category='purpose'):
    """
    Centralized Reference Table & Dropdown Manager replicating Patient Scheduler database design.
    Allows Admins to manage and reorder Discussion Purposes, Sites, Modalities, Specimens, etc.
    """
    if not is_admin_user(request.user):
        messages.error(request, "Access denied: Dropdown management requires Administrator privileges.")
        return redirect('dashboard')

    if category not in LOOKUP_CONFIG:
        category = 'purpose'

    cfg = get_lookup_config(category)
    model = cfg['model']
    pk_field = cfg['pk']
    name_field = cfg['name_field']

    items = model.objects.all().order_by('display_order', name_field)
    processed_items = []
    for it in items:
        processed_items.append({
            'pk': getattr(it, pk_field),
            'name': getattr(it, name_field),
            'display_order': getattr(it, 'display_order', 0),
            'is_active': getattr(it, 'is_active', True),
        })

    context = {
        'category': category,
        'cfg': cfg,
        'items': processed_items,
        'lookup_categories': LOOKUP_CONFIG,
    }
    return render(request, 'mdt/lookup_manager.html', context)


@login_required
def lookup_add_view(request, category):
    if not is_admin_user(request.user):
        messages.error(request, "Access denied: Administrators only.")
        return redirect('dashboard')

    if request.method == 'POST':
        cfg = get_lookup_config(category)
        model = cfg['model']
        name_field = cfg['name_field']

        name_val = request.POST.get('name_value', '').strip()
        display_order = request.POST.get('display_order', '').strip()
        is_active = bool(request.POST.get('is_active'))

        if not name_val:
            messages.error(request, "Option name cannot be empty.")
            return redirect('lookup_manager_category', category=category)

        try:
            order_num = int(display_order) if display_order else model.objects.count() + 1
        except ValueError:
            order_num = model.objects.count() + 1

        obj, created = model.objects.get_or_create(
            **{name_field: name_val},
            defaults={'display_order': order_num, 'is_active': is_active}
        )
        if not created and not obj.is_active and is_active:
            obj.is_active = True
            obj.save()

        write_audit_log(
            request.user, "ADD_LOOKUP", cfg['table_name'], name_val,
            f"Added {cfg['title']} option '{name_val}'."
        )
        messages.success(request, f"Option '{name_val}' saved to {cfg['title']}.")

    return redirect('lookup_manager_category', category=category)


@login_required
def lookup_toggle_view(request, category, item_id):
    if not is_admin_user(request.user):
        messages.error(request, "Access denied: Administrators only.")
        return redirect('dashboard')

    if request.method == 'POST':
        cfg = get_lookup_config(category)
        model = cfg['model']
        pk_field = cfg['pk']
        name_field = cfg['name_field']

        item = get_object_or_404(model, **{pk_field: item_id})
        item.is_active = not item.is_active
        item.save()

        status_str = "Activated" if item.is_active else "Deactivated"
        write_audit_log(
            request.user, "TOGGLE_LOOKUP", cfg['table_name'], str(getattr(item, name_field)),
            f"{status_str} in {cfg['title']}."
        )
        messages.success(request, f"Option '{getattr(item, name_field)}' {status_str.lower()}.")

    return redirect('lookup_manager_category', category=category)


@login_required
def lookup_delete_view(request, category, item_id):
    if not is_admin_only(request.user):
        messages.error(request, "Access denied: Only full Administrators can delete lookup options.")
        return redirect('lookup_manager_category', category=category)

    if request.method == 'POST':
        cfg = get_lookup_config(category)
        model = cfg['model']
        pk_field = cfg['pk']
        name_field = cfg['name_field']

        item = get_object_or_404(model, **{pk_field: item_id})
        name_val = getattr(item, name_field)
        try:
            item.delete()
            write_audit_log(
                request.user, "DELETE_LOOKUP", cfg['table_name'], str(name_val),
                f"Permanently deleted option '{name_val}' from {cfg['title']}."
            )
            messages.success(request, f"Option '{name_val}' permanently deleted.")
        except Exception:
            messages.error(request, f"Cannot delete '{name_val}': option is linked to existing records. Deactivate it instead.")

    return redirect('lookup_manager_category', category=category)


@login_required
def lookup_reorder_view(request, category):
    if not is_admin_user(request.user):
        return JsonResponse({'error': 'Access denied: Administrators only'}, status=403)

    if request.method == 'POST':
        cfg = get_lookup_config(category)
        model = cfg['model']
        pk_field = cfg['pk']

        order_ids = []
        try:
            if request.body:
                data = json.loads(request.body)
                order_ids = data.get('order', [])
        except Exception:
            pass

        if not order_ids:
            order_ids = request.POST.getlist('order') or request.POST.getlist('order[]')

        if not order_ids:
            return JsonResponse({'error': 'No order sequence provided'}, status=400)

        with transaction.atomic():
            for idx, pid in enumerate(order_ids, start=1):
                try:
                    model.objects.filter(**{pk_field: int(pid)}).update(display_order=idx)
                except (ValueError, TypeError):
                    continue

        write_audit_log(
            request.user, "REORDER_LOOKUP", cfg['table_name'], f"{len(order_ids)} items",
            f"Admin reordered {cfg['title']} options via drag-and-drop."
        )
        return JsonResponse({'status': 'ok', 'message': f"{cfg['title']} display order saved."})

    return JsonResponse({'error': 'POST method required'}, status=405)


# ==========================================
# Gynae-Style Multi-Modality Investigation Pages
# ==========================================

@login_required
def investigations_hub_view(request, clinical_id):
    """
    Dedicated Multi-Modality Diagnostic Workup Hub (replicates Gynae database design).
    Tabs for Blood, Imaging, Pathology, and Molecular investigations with clean Access workstation style.
    """
    clinical = get_object_or_404(ClinicalDetails.objects.select_related('patient'), clinical_id=clinical_id)
    patient = clinical.patient
    active_tab = request.GET.get('tab', 'blood')
    if active_tab not in ['blood', 'imaging', 'pathology', 'molecular']:
        active_tab = 'blood'

    context = {
        'clinical': clinical,
        'patient': patient,
        'active_tab': active_tab,
        'blood_tests': clinical.blood_tests.all(),
        'imaging_tests': clinical.imaging_tests.all(),
        'pathology_tests': clinical.pathology_tests.all(),
        'molecular_tests': clinical.molecular_tests.all(),
        'is_approved': clinical.status == 'Approved',
    }
    return render(request, 'mdt/investigations/investigations_hub.html', context)


@login_required
def blood_form_view(request, clinical_id, inv_id=None):
    clinical = get_object_or_404(ClinicalDetails.objects.select_related('patient'), clinical_id=clinical_id)
    patient = clinical.patient
    is_approved = clinical.status == 'Approved'
    if is_approved:
        messages.error(request, "Cannot modify investigations for an Approved clinical record.")
        return redirect('investigations_hub', clinical_id=clinical_id)

    instance = get_object_or_404(BloodInvestigation, id=inv_id, clinical_details=clinical) if inv_id else None

    if request.method == 'POST':
        form = BloodInvestigationForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            inv = form.save(commit=False)
            inv.clinical_details = clinical
            inv.entered_by = request.user.username
            inv.save()
            verb = "updated" if instance else "recorded"
            write_audit_log(request.user, f"{'EDIT' if instance else 'ADD'}_BLOOD", "tblBloodInvestigation", patient.mr_no, f"Inv ID: {inv.id}")
            messages.success(request, f"Blood investigation {verb} successfully.")
            return redirect(f"{reverse('investigations_hub', kwargs={'clinical_id': clinical_id})}?tab=blood")
        else:
            for field, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{field}: {err}")
    else:
        form = BloodInvestigationForm(instance=instance, initial={'test_date': date.today()} if not instance else {})

    context = {
        'form': form,
        'clinical': clinical,
        'patient': patient,
        'instance': instance,
        'is_edit': bool(instance),
    }
    return render(request, 'mdt/investigations/blood_form.html', context)


@login_required
def imaging_form_view(request, clinical_id, inv_id=None):
    clinical = get_object_or_404(ClinicalDetails.objects.select_related('patient'), clinical_id=clinical_id)
    patient = clinical.patient
    is_approved = clinical.status == 'Approved'
    if is_approved:
        messages.error(request, "Cannot modify investigations for an Approved clinical record.")
        return redirect('investigations_hub', clinical_id=clinical_id)

    instance = get_object_or_404(ImagingInvestigation, id=inv_id, clinical_details=clinical) if inv_id else None

    if request.method == 'POST':
        form = ImagingInvestigationForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            inv = form.save(commit=False)
            inv.clinical_details = clinical
            inv.entered_by = request.user.username
            inv.save()
            verb = "updated" if instance else "recorded"
            write_audit_log(request.user, f"{'EDIT' if instance else 'ADD'}_IMAGING", "tblImagingInvestigation", patient.mr_no, f"Inv ID: {inv.id}")
            messages.success(request, f"Imaging investigation {verb} successfully.")
            return redirect(f"{reverse('investigations_hub', kwargs={'clinical_id': clinical_id})}?tab=imaging")
        else:
            for field, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{field}: {err}")
    else:
        form = ImagingInvestigationForm(instance=instance, initial={'imaging_date': date.today()} if not instance else {})

    context = {
        'form': form,
        'clinical': clinical,
        'patient': patient,
        'instance': instance,
        'is_edit': bool(instance),
    }
    return render(request, 'mdt/investigations/imaging_form.html', context)


@login_required
def pathology_form_view(request, clinical_id, inv_id=None):
    clinical = get_object_or_404(ClinicalDetails.objects.select_related('patient'), clinical_id=clinical_id)
    patient = clinical.patient
    is_approved = clinical.status == 'Approved'
    if is_approved:
        messages.error(request, "Cannot modify investigations for an Approved clinical record.")
        return redirect('investigations_hub', clinical_id=clinical_id)

    instance = get_object_or_404(PathologyInvestigation, id=inv_id, clinical_details=clinical) if inv_id else None

    if request.method == 'POST':
        form = PathologyInvestigationForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            inv = form.save(commit=False)
            inv.clinical_details = clinical
            inv.entered_by = request.user.username
            inv.save()
            verb = "updated" if instance else "recorded"
            write_audit_log(request.user, f"{'EDIT' if instance else 'ADD'}_PATHOLOGY", "tblPathologyInvestigation", patient.mr_no, f"Inv ID: {inv.id}")
            messages.success(request, f"Pathology investigation {verb} successfully.")
            return redirect(f"{reverse('investigations_hub', kwargs={'clinical_id': clinical_id})}?tab=pathology")
        else:
            for field, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{field}: {err}")
    else:
        form = PathologyInvestigationForm(instance=instance, initial={'path_date': date.today()} if not instance else {})

    context = {
        'form': form,
        'clinical': clinical,
        'patient': patient,
        'instance': instance,
        'is_edit': bool(instance),
    }
    return render(request, 'mdt/investigations/pathology_form.html', context)


@login_required
def molecular_form_view(request, clinical_id, inv_id=None):
    clinical = get_object_or_404(ClinicalDetails.objects.select_related('patient'), clinical_id=clinical_id)
    patient = clinical.patient
    is_approved = clinical.status == 'Approved'
    if is_approved:
        messages.error(request, "Cannot modify investigations for an Approved clinical record.")
        return redirect('investigations_hub', clinical_id=clinical_id)

    instance = get_object_or_404(MolecularInvestigation, id=inv_id, clinical_details=clinical) if inv_id else None

    if request.method == 'POST':
        form = MolecularInvestigationForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            inv = form.save(commit=False)
            inv.clinical_details = clinical
            inv.entered_by = request.user.username
            inv.save()
            verb = "updated" if instance else "recorded"
            write_audit_log(request.user, f"{'EDIT' if instance else 'ADD'}_MOLECULAR", "tblMolecularInvestigation", patient.mr_no, f"Inv ID: {inv.id}")
            messages.success(request, f"Molecular investigation {verb} successfully.")
            return redirect(f"{reverse('investigations_hub', kwargs={'clinical_id': clinical_id})}?tab=molecular")
        else:
            for field, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{field}: {err}")
    else:
        form = MolecularInvestigationForm(instance=instance, initial={'test_date': date.today()} if not instance else {})

    context = {
        'form': form,
        'clinical': clinical,
        'patient': patient,
        'instance': instance,
        'is_edit': bool(instance),
    }
    return render(request, 'mdt/investigations/molecular_form.html', context)

