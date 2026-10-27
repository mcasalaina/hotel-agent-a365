@description('Name of the controlled ASSERT Container Apps Job.')
param jobName string = 'hotel-agent-assert'

@description('Location of the existing Container Apps managed environment.')
param location string

@description('Resource ID of an existing Container Apps managed environment.')
param environmentId string

@description('Runner image containing this repository and the pinned ASSERT build.')
param runnerImage string

@description('Container registry server, for example contoso.azurecr.io.')
param registryServer string

@description('User-assigned managed identity resource ID used by the runner and registry.')
param workloadIdentityResourceId string

@description('Client ID of the runner user-assigned managed identity.')
param workloadIdentityClientId string

@description('Container Apps environment storage name backed by restricted Azure Files.')
param environmentStorageName string

@description('Foundry project endpoint used by the Hosted Agent protocol.')
param foundryEndpoint string

@description('Azure OpenAI endpoint used by ASSERT generation and judging.')
param judgeModelEndpoint string

@description('Foundry access-token audience claim expected from Agent ID.')
param foundryAudience string

@description('Log Analytics workspace ID for Application Insights trace queries.')
param logAnalyticsWorkspaceId string

@description('Tenant containing the Hotel Guest Services Agent ID user.')
param tenantId string

@description('Parent blueprint client ID.')
param parentBlueprintClientId string

@description('Key Vault secret URI containing the parent blueprint credential.')
param parentBlueprintSecretUri string

@description('Agent identity client ID.')
param agentIdentityId string

@description('Agent-user object ID.')
param agentUserId string

@description('Optional ASSERT run ID used to resume an existing run.')
param runIdOverride string = ''

@description('Hosted Agent name.')
param hostedAgentName string = 'hotel-servicing-agent'

@description('Model deployment used by the Hosted Agent request.')
param hostedAgentModel string = 'gpt-5.4-mini'

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${workloadIdentityResourceId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 7200
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registryServer
          identity: workloadIdentityResourceId
        }
      ]
      secrets: [
        {
          name: 'blueprint-client-secret'
          keyVaultUrl: parentBlueprintSecretUri
          identity: workloadIdentityResourceId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'assert-runner'
          image: runnerImage
          resources: {
            cpu: 1
            memory: '2Gi'
          }
          args: concat(
            [
              'live'
              '--config'
              'evaluation/assert/config/baseline-quality.yaml'
              '--suite'
              'hotel-guest-services-conversations'
              '--require-all-cases'
              '25'
            ],
            empty(runIdOverride) ? [] : [
              '--run-id'
              runIdOverride
            ]
          )
          volumeMounts: [
            {
              volumeName: 'assert-artifacts'
              mountPath: '/workspace/artifacts'
            }
          ]
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: workloadIdentityClientId
            }
            {
              name: 'ASSERT_AZURE_USE_AAD'
              value: '1'
            }
            {
              name: 'AZURE_API_BASE'
              value: judgeModelEndpoint
            }
            {
              name: 'AZURE_AI_FOUNDRY_ENDPOINT'
              value: foundryEndpoint
            }
            {
              name: 'FOUNDRY_AGENT_NAME'
              value: hostedAgentName
            }
            {
              name: 'FOUNDRY_MODEL_NAME'
              value: hostedAgentModel
            }
            {
              name: 'ASSERT_TENANT_ID'
              value: tenantId
            }
            {
              name: 'ASSERT_FOUNDRY_AUDIENCE'
              value: foundryAudience
            }
            {
              name: 'ASSERT_AGENT_USER_ID'
              value: agentUserId
            }
            {
              name: 'ASSERT_AGENT_IDENTITY_ID'
              value: agentIdentityId
            }
            {
              name: 'ASSERT_PARENT_BLUEPRINT_ID'
              value: parentBlueprintClientId
            }
            {
              name: 'ASSERT_SIDECAR_URL'
              value: 'http://127.0.0.1:5000'
            }
            {
              name: 'APPLICATIONINSIGHTS_WORKSPACE_ID'
              value: logAnalyticsWorkspaceId
            }
            {
              name: 'ASPNETCORE_ENVIRONMENT'
              value: 'Production'
            }
            {
              name: 'ASPNETCORE_URLS'
              value: 'http://127.0.0.1:5000'
            }
            {
              name: 'Sidecar__AllowOverrides__GetAuthorizationHeaderUnauthenticated'
              value: 'true'
            }
            {
              name: 'AzureAd__Instance'
              value: environment().authentication.loginEndpoint
            }
            {
              name: 'AzureAd__TenantId'
              value: tenantId
            }
            {
              name: 'AzureAd__ClientId'
              value: parentBlueprintClientId
            }
            {
              name: 'AzureAd__ClientCredentials__0__SourceType'
              value: 'ClientSecret'
            }
            {
              name: 'AzureAd__ClientCredentials__0__ClientSecret'
              secretRef: 'blueprint-client-secret'
            }
            {
              name: 'DownstreamApis__Foundry__BaseUrl'
              value: foundryEndpoint
            }
            {
              name: 'DownstreamApis__Foundry__Scopes__0'
              value: 'https://ai.azure.com/.default'
            }
            {
              name: 'Logging__LogLevel__Default'
              value: 'Information'
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'assert-artifacts'
          storageType: 'AzureFile'
          storageName: environmentStorageName
        }
      ]
    }
  }
}

output jobId string = job.id
output jobName string = job.name
