targetScope = 'resourceGroup'

@description('Azure region for the Voice Live web application.')
param location string = resourceGroup().location

@description('Fully qualified container image, including the registry and immutable tag.')
param imageName string

@description('Microsoft Entra tenant that issues browser access tokens.')
param entraTenantId string

@description('Application client ID of the Entra API registration.')
param entraApiClientId string

@description('Existing Azure Container Registry resource group.')
param containerRegistryResourceGroupName string = 'rg-mcasalaina-4iqs-2701'

@description('Existing Azure Container Registry name.')
param containerRegistryName string = 'mcasalaina4iqs2701acr'

@description('Existing Microsoft Foundry project endpoint.')
param foundryProjectEndpoint string = 'https://mcasalaina-4iqs-2701-resource.services.ai.azure.com/api/projects/mcasalaina-4iqs-2701'

@description('Hosted Agent name.')
param foundryAgentName string = 'hotel-servicing-agent'

@description('Container Apps environment name.')
param managedEnvironmentName string = 'hotel-voice-env'

@description('Create a dedicated environment, or reuse an existing environment without changing it.')
param createManagedEnvironment bool = true

@description('Resource group containing the existing Container Apps environment when reusing one.')
param managedEnvironmentResourceGroupName string = resourceGroup().name

@description('Container App name.')
param containerAppName string = 'hotel-voice-proxy'

@description('User-assigned identity name.')
param managedIdentityName string = 'hotel-voice-proxy-identity'

var tags = {
  application: 'hotel-agent-a365'
  component: 'voice-web'
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
  scope: resourceGroup(subscription().subscriptionId, containerRegistryResourceGroupName)
}

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: managedIdentityName
  location: location
  tags: tags
}

module registryPullRole 'modules/voice-web-acr-role.bicep' = {
  name: 'voice-web-acr-pull'
  scope: resourceGroup(subscription().subscriptionId, containerRegistryResourceGroupName)
  params: {
    containerRegistryName: containerRegistryName
    principalId: managedIdentity.properties.principalId
    managedIdentityResourceId: managedIdentity.id
  }
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = if (createManagedEnvironment) {
  name: managedEnvironmentName
  location: location
  tags: tags
  properties: {}
}

resource existingManagedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: managedEnvironmentName
  scope: resourceGroup(subscription().subscriptionId, managedEnvironmentResourceGroupName)
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: createManagedEnvironment ? managedEnvironment!.id : existingManagedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8080
        transport: 'auto'
        stickySessions: {
          affinity: 'sticky'
        }
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: managedIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'voice-proxy'
          image: imageName
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentity.properties.clientId
            }
            {
              name: 'ENTRA_TENANT_ID'
              value: entraTenantId
            }
            {
              name: 'ENTRA_API_AUDIENCE'
              value: entraApiClientId
            }
            {
              name: 'ENTRA_REQUIRED_SCOPE'
              value: 'HotelAgent.Access'
            }
            {
              name: 'FOUNDRY_PROJECT_ENDPOINT'
              value: foundryProjectEndpoint
            }
            {
              name: 'FOUNDRY_AGENT_NAME'
              value: foundryAgentName
            }
            {
              name: 'VOICE_PROXY_ENVIRONMENT'
              value: 'production'
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/api/health'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 1
              periodSeconds: 2
              failureThreshold: 30
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/health'
                port: 8080
                scheme: 'HTTP'
              }
              periodSeconds: 30
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 2
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [
    registryPullRole
  ]
}

output VOICE_WEB_URL string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output VOICE_WEB_HOSTNAME string = containerApp.properties.configuration.ingress.fqdn
output VOICE_WEB_IDENTITY_CLIENT_ID string = managedIdentity.properties.clientId
output VOICE_WEB_IDENTITY_PRINCIPAL_ID string = managedIdentity.properties.principalId
