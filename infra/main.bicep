targetScope = 'subscription'

@description('Name of the azd environment.')
param environmentName string

@description('Azure region for new supporting resources.')
param location string = 'eastus2'

@description('Resource group for hotel-agent supporting resources.')
param supportResourceGroupName string = 'rg-hotel-agent-a365'

@description('Resource group containing the existing Foundry project.')
param foundryResourceGroupName string = 'rg-aycabas-3iqs'

@description('Name of the existing Foundry account.')
param foundryAccountName string = '4iq-foundry-project-resource'

@description('Name of the existing Foundry project.')
param foundryProjectName string = '4iq-foundry-project'

@description('Object ID of the principal running azd.')
param deploymentPrincipalId string

var resourceSuffix = uniqueString(subscription().id, supportResourceGroupName)
var searchServiceName = toLower('hotel-search-${resourceSuffix}')
var storageAccountName = toLower('hoteldocs${resourceSuffix}')
var tags = {
  'azd-env-name': environmentName
  application: 'hotel-agent-a365'
}

resource supportResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: supportResourceGroupName
  location: location
  tags: tags
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
  scope: resourceGroup(subscription().subscriptionId, foundryResourceGroupName)
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundryAccount
  name: foundryProjectName
}

module supportingResources 'modules/supporting-resources.bicep' = {
  name: 'supporting-resources'
  scope: supportResourceGroup
  params: {
    location: location
    searchServiceName: searchServiceName
    storageAccountName: storageAccountName
    foundryProjectPrincipalId: foundryProject.identity.principalId!
    deploymentPrincipalId: deploymentPrincipalId
    tags: tags
  }
}

module foundryConnection 'modules/foundry-connection.bicep' = {
  name: 'foundry-search-connection'
  scope: resourceGroup(subscription().subscriptionId, foundryResourceGroupName)
  params: {
    foundryAccountName: foundryAccountName
    foundryProjectName: foundryProjectName
    searchConnectionName: 'hotel-search'
    searchServiceEndpoint: supportingResources.outputs.searchServiceEndpoint
    searchServiceId: supportingResources.outputs.searchServiceId
    searchServiceLocation: location
  }
}

output AZURE_RESOURCE_GROUP string = supportResourceGroup.name
output AZURE_SEARCH_SERVICE_ENDPOINT string = supportingResources.outputs.searchServiceEndpoint
output AZURE_SEARCH_SERVICE_NAME string = supportingResources.outputs.searchServiceName
output AZURE_STORAGE_ACCOUNT_NAME string = supportingResources.outputs.storageAccountName
output HOTEL_DOCUMENT_CONTAINER_NAME string = supportingResources.outputs.documentContainerName
output HOTEL_SEARCH_CONNECTION_NAME string = foundryConnection.outputs.searchConnectionName
