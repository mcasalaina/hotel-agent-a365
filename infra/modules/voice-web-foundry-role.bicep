targetScope = 'resourceGroup'

param foundryAccountName string
param foundryProjectName string
param principalId string
param managedIdentityResourceId string

var azureAiDeveloperRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '64702f94-c441-49e6-a78b-ef80e0188fee'
)

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundryAccount
  name: foundryProjectName
}

resource foundryDeveloperRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryProject.id, managedIdentityResourceId, azureAiDeveloperRoleDefinitionId)
  scope: foundryProject
  properties: {
    roleDefinitionId: azureAiDeveloperRoleDefinitionId
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
