targetScope = 'resourceGroup'

param location string = resourceGroup().location
param jobName string = 'hotel-agent-vault-bootstrap'
param managedEnvironmentResourceId string
param userAssignedIdentityResourceId string
param userAssignedIdentityClientId string
param registryServer string
param containerImage string
param keyVaultUrl string
param blueprintObjectId string
param appInsightsResourceId string
param privateEndpointSubnet string = '10.86.8.0/24'

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityResourceId}': {}
    }
  }
  properties: {
    environmentId: managedEnvironmentResourceId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 600
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registryServer
          identity: userAssignedIdentityResourceId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'vault-bootstrap'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: userAssignedIdentityClientId
            }
            {
              name: 'KEY_VAULT_URL'
              value: keyVaultUrl
            }
            {
              name: 'BLUEPRINT_OBJECT_ID'
              value: blueprintObjectId
            }
            {
              name: 'APPINSIGHTS_RESOURCE_ID'
              value: appInsightsResourceId
            }
            {
              name: 'PRIVATE_ENDPOINT_SUBNET'
              value: privateEndpointSubnet
            }
          ]
        }
      ]
    }
  }
}

output jobName string = job.name
output jobResourceId string = job.id
