from apps.api_tokens.models import APIToken
from apps.organizations_ext.constants import OrganizationUserRole
from apps.organizations_ext.models import Organization
from apps.projects.models import Project
from apps.users.models import User

user, _ = User.objects.get_or_create(email="e2e@example.com", defaults={"is_superuser": True})
org, created = Organization.objects.get_or_create(slug="e2e", defaults={"name": "e2e"})
if created:
    org.add_user(user, role=OrganizationUserRole.OWNER)
for slug in ("api", "web"):
    Project.objects.get_or_create(organization=org, slug=slug, defaults={"name": slug})
token, _ = APIToken.objects.get_or_create(user=user, label="e2e")
for scope in ("project:read", "project:write", "project:admin"):
    token.add_permission(scope)
print(f"TOKEN={token.token}")
