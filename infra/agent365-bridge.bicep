targetScope = 'resourceGroup'

param location string = resourceGroup().location
param containerAppName string = 'hotel-agent-bridge-a365'
param managedEnvironmentResourceId string
param userAssignedIdentityResourceId string
param userAssignedIdentityClientId string
param registryServer string
param containerImage string
param blueprintSecretUri string
param appInsightsSecretUri string
param tenantId string
param blueprintClientId string
param foundryEndpoint string
param foundryAgentName string = 'hotel-servicing-agent'
param foundryModelName string = 'gpt-5.4-mini'

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityResourceId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironmentResourceId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 3978
        transport: 'Auto'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: registryServer
          identity: userAssignedIdentityResourceId
        }
      ]
      secrets: [
        {
          name: 'blueprint-secret'
          keyVaultUrl: blueprintSecretUri
          identity: userAssignedIdentityResourceId
        }
        {
          name: 'appinsights-cs'
          keyVaultUrl: appInsightsSecretUri
          identity: userAssignedIdentityResourceId
        }
      ]
    }
    template: {
      containers: [
        {
          name: containerAppName
          image: containerImage
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: userAssignedIdentityClientId
            }
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
              secretRef: 'blueprint-secret'
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
              secretRef: 'blueprint-secret'
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
              name: 'A365_USE_S2S_ENDPOINT'
              value: 'true'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-cs'
            }
            {
              name: 'PYTHON_ENVIRONMENT'
              value: 'production'
            }
            {
              name: 'PORT'
              value: '3978'
            }
            {
              name: 'WEBSITES_PORT'
              value: '3978'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output containerAppName string = containerApp.name
output userAssignedIdentityId string = userAssignedIdentityResourceId
output messagingEndpoint string = 'https://${containerApp.properties.configuration.ingress.fqdn}/api/messages'
