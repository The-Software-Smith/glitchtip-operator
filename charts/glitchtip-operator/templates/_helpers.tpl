{{- define "glitchtip-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "glitchtip-operator.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if contains (include "glitchtip-operator.name" .) .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "glitchtip-operator.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "glitchtip-operator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "glitchtip-operator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "glitchtip-operator.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{ include "glitchtip-operator.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "glitchtip-operator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "glitchtip-operator.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "glitchtip-operator.tokenSecret" -}}
{{- default (include "glitchtip-operator.fullname" .) .Values.glitchtip.existingSecret }}
{{- end }}

{{- define "glitchtip-operator.namespacedRules" -}}
- apiGroups: [glitchtip.softwaresmith.io]
  resources: [projectalerts]
  verbs: [get, list, watch, patch, update]
- apiGroups: [glitchtip.softwaresmith.io]
  resources: [projectalerts/status]
  verbs: [get, patch, update]
- apiGroups: [""]
  resources: [secrets]
  verbs: [get]
- apiGroups: ["", events.k8s.io]
  resources: [events]
  verbs: [create]
{{- end }}
