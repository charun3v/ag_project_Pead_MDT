from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Patient URLs
    path('patients/search/', views.patient_search, name='patient_search'),
    path('patients/new/', views.patient_create, name='patient_create'),
    path('patients/<str:mr_no>/edit/', views.patient_edit, name='patient_edit'),
    path('api/districts/', views.api_districts, name='api_districts'),
    
    # Clinical Presentation URLs
    path('clinical/new/<str:mr_no>/', views.clinical_create, name='clinical_create'),
    path('clinical/<int:clinical_id>/', views.clinical_edit, name='clinical_edit'),
    path('clinical/<int:clinical_id>/inv/add/<str:inv_type>/', views.investigation_add, name='investigation_add'),
    path('investigation/delete/<str:inv_type>/<int:inv_id>/', views.investigation_delete, name='investigation_delete'),
    
    # MDT Consensus URLs
    path('consensus/<int:consensus_id>/', views.consensus_edit, name='consensus_edit'),
    path('consensus/<int:consensus_id>/live/', views.live_presentation, name='live_presentation'),
    
    # Reports
    path('reports/clinical/<int:clinical_id>/', views.report_clinical_summary, name='report_clinical_summary'),
    path('reports/mdt/<int:consensus_id>/', views.report_mdt_full, name='report_mdt_full'),
    
    # Audit Logs
    path('audit-log/', views.audit_log_view, name='audit_log_view'),
]
