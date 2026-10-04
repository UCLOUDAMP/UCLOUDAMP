# Deployment prerequisites and operator steps

This first slice keeps deployment disabled. The repository builds `dist/` only.

## Verified references used for this plan

- Azure Static Web Apps build configuration (Microsoft Learn / MicrosoftDocs):
  - https://learn.microsoft.com/en-us/azure/static-web-apps/build-configuration
  - https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/static-web-apps/build-configuration.md
- Azure Static Web Apps configuration file behavior:
  - https://learn.microsoft.com/en-us/azure/static-web-apps/configuration
  - https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/static-web-apps/configuration.md
- Deployment token management:
  - https://learn.microsoft.com/en-us/azure/static-web-apps/deployment-token-management
  - https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/static-web-apps/deployment-token-management.md
- Custom authentication behavior and plan constraints:
  - https://learn.microsoft.com/en-us/azure/static-web-apps/authentication-custom
  - https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/static-web-apps/authentication-custom.md

## Prerequisites (not performed here)

1. Existing Azure subscription and an Azure Static Web Apps resource.
2. Repository secret containing deployment token (`AZURE_STATIC_WEB_APPS_API_TOKEN...`) if token-based deployment is selected.
3. Explicit owner decision on deployment authorization policy and authentication provider setup.
4. Confirmed branch/environment release policy for public publication.

## Operator steps for deploying already-built artifacts

1. Run local/CI build to produce `dist/`.
2. Ensure `staticwebapp.config.json` is present at `dist/staticwebapp.config.json`.
3. Configure Azure Static Web Apps deployment to upload the already-built directory:
   - Set `app_location` to `dist`
   - Set `skip_app_build: true`
4. Keep deployment credentials in GitHub secrets or OIDC configuration only; never commit secrets.
5. Trigger deployment only after review and approval.

## Explicit unresolved blockers

- Authentication mode is not selected for public release:
  - Managed/default provider flow vs custom identity provider configuration remains an owner decision.
  - If custom auth is required, Microsoft documentation states Standard plan requirements and app settings must be configured first.
- Final deployment authorization policy (deployment token vs identity token) is not yet selected.
- DNS cutover and publication timing are intentionally out of scope for this slice.
