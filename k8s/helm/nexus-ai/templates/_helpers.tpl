{{/*
_helpers.tpl — Helm template helpers cho Nexus AI chart.
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "nexus-ai.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "nexus-ai.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "nexus-ai.labels" -}}
helm.sh/chart: {{ include "nexus-ai.name" . }}-{{ .Chart.Version }}
app.kubernetes.io/name: {{ include "nexus-ai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
