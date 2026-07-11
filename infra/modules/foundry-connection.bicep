targetScope = 'resourceGroup'

@description('Name of the existing Foundry account.')
param foundryAccountName string

@description('Name of the existing Foundry project.')
param foundryProjectName string

@description('Name of the Foundry project connection.')
param searchConnectionName string

@description('Azure AI Search endpoint.')
param searchServiceEndpoint string

@description('Azure AI Search resource ID.')
param searchServiceId string

@description('Azure region containing the Search service.')
param searchServiceLocation string

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundryAccount
  name: foundryProjectName
}

resource searchConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: foundryProject
  name: searchConnectionName
  properties: {
    authType: 'AAD'
    category: 'CognitiveSearch'
    isSharedToAll: false
    metadata: {
      ApiType: 'Azure'
      ResourceId: searchServiceId
      location: searchServiceLocation
    }
    target: searchServiceEndpoint
    useWorkspaceManagedIdentity: true
  }
}

output searchConnectionName string = searchConnection.name
