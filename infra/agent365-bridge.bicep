targetScope = 'resourceGroup'

param location string = resourceGroup().location
param appServiceName string = 'hotel-agent-bridge-a365'
param appServicePlanName string = 'hotel-agent-bridge-plan'
param appServicePlanSkuName string = 'F1'
param appServicePlanSkuTier string = 'Free'
param tenantId string
param blueprintClientId string
@secure()
param blueprintClientSecret string
param foundryEndpoint string = 'https://4iq-foundry-project-resource.services.ai.azure.com/api/projects/4iq-foundry-project'
param foundryAgentName string = 'hotel-servicing-agent'
param foundryModelName string = 'gpt-5.4-mini'
@secure()
param appInsightsConnectionString string = ''

resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: appServicePlanName
  location: location
  kind: 'linux'
  sku: {
    name: appServicePlanSkuName
    tier: appServicePlanSkuTier
  }
  properties: {
    reserved: true
  }
}

resource appService 'Microsoft.Web/sites@2023-12-01' = {
  name: appServiceName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      alwaysOn: appServicePlanSkuName != 'F1'
      ftpsState: 'Disabled'
      linuxFxVersion: 'PYTHON|3.12'
      webSocketsEnabled: true
      appCommandLine: 'cd agent && pip install --disable-pip-version-check -q -r requirements.txt && python start_with_generic_host.py'
      appSettings: [
        {
          name: 'AZURE_AI_FOUNDRY_ENDPOINT'
          value: foundryEndpoint
        }
        {
          name: 'FOUNDRY_AGENT_NAME'
          value: foundryAgentName
        }
        {
          name: 'FOUNDRY_MODEL_NAME'
          value: foundryModelName
        }
        {
          name: 'FOUNDRY_USER_TOKEN_SCOPES'
          value: 'https://ai.azure.com/.default'
        }
        {
          name: 'CLIENT_ID'
          value: blueprintClientId
        }
        {
          name: 'CLIENT_SECRET'
          value: blueprintClientSecret
        }
        {
          name: 'TENANT_ID'
          value: tenantId
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID'
          value: blueprintClientId
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET'
          value: blueprintClientSecret
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID'
          value: tenantId
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__SCOPES'
          value: '5a807f24-c9de-44ee-a3a7-329e88a00ffc/.default'
        }
        {
          name: 'CONNECTIONSMAP__0__SERVICEURL'
          value: '*'
        }
        {
          name: 'CONNECTIONSMAP__0__CONNECTION'
          value: 'SERVICE_CONNECTION'
        }
        {
          name: 'AUTH_HANDLER_NAME'
          value: 'AGENTIC'
        }
        {
          name: 'AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__TYPE'
          value: 'AgenticUserAuthorization'
        }
        {
          name: 'AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__SCOPES'
          value: 'https://graph.microsoft.com/.default'
        }
        {
          name: 'AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__ALT_BLUEPRINT_NAME'
          value: 'SERVICE_CONNECTION'
        }
        {
          name: 'ENABLE_OBSERVABILITY'
          value: 'true'
        }
        {
          name: 'ENABLE_A365_OBSERVABILITY_EXPORTER'
          value: 'true'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsightsConnectionString
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'false'
        }
        {
          name: 'WEBSITES_PORT'
          value: '3978'
        }
        {
          name: 'PORT'
          value: '3978'
        }
      ]
    }
  }
}

output appServiceName string = appService.name
output appServicePrincipalId string = appService.identity.principalId
output messagingEndpoint string = 'https://${appService.properties.defaultHostName}/api/messages'
