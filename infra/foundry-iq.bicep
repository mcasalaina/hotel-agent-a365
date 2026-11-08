targetScope = 'resourceGroup'

@description('Region for the approved dedicated Search and document archive.')
param location string = resourceGroup().location

@description('Search-only regional override if new service capacity is unavailable.')
param searchLocation string = location

@description('Existing Foundry account; this deployment never creates it.')
param foundryAccountName string

@description('Existing Foundry project; this deployment never creates it.')
param foundryProjectName string

@description('Object ID of the verified Foundry project managed identity.')
param foundryProjectPrincipalId string

@description('Object ID of the setup/content-loading principal.')
param deploymentPrincipalId string

@description('Globally unique Azure AI Search service name.')
param searchServiceName string = 'hotel-iq-${uniqueString(resourceGroup().id)}'

@description('Globally unique private document archive account name.')
param storageAccountName string = 'sthoteliq${uniqueString(resourceGroup().id)}'

@description('Create the archive on the first deployment; false preserves an existing archive.')
param deployArchive bool = true

@description('AAD project Search connection name.')
param searchConnectionName string = 'hotel-search-connection'

param tags object = {}

var searchServiceContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
)
var searchIndexDataContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
)
var searchIndexDataReaderRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions', '1407120a-92aa-4202-b7e9-c0e197c71c8f'
)
var storageBlobDataContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
)
var cognitiveServicesUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908'
)

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource searchService 'Microsoft.Search/searchServices@2025-05-01' = {
  name: searchServiceName
  location: searchLocation
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'standard'
  }
  properties: {
    disableLocalAuth: true
    hostingMode: 'Default'
    partitionCount: 1
    publicNetworkAccess: 'Enabled'
    replicaCount: 1
    semanticSearch: 'standard'
  }
}

resource existingArchive 'Microsoft.Storage/storageAccounts@2025-06-01' existing = {
  name: storageAccountName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-06-01' = if (deployArchive) {
  name: storageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-06-01' = if (deployArchive) {
  parent: storageAccount
  name: 'default'
  properties: {
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource documentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = if (deployArchive) {
  parent: blobService
  name: 'hotel-docs'
  properties: {
    publicAccess: 'None'
  }
}

resource projectSearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, foundryProjectPrincipalId, searchIndexDataReaderRoleId)
  scope: searchService
  properties: {
    principalId: foundryProjectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: searchIndexDataReaderRoleId
  }
}

resource deployerSearchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, deploymentPrincipalId, searchServiceContributorRoleId)
  scope: searchService
  properties: {
    principalId: deploymentPrincipalId
    roleDefinitionId: searchServiceContributorRoleId
  }
}

resource deployerSearchDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, deploymentPrincipalId, searchIndexDataContributorRoleId)
  scope: searchService
  properties: {
    principalId: deploymentPrincipalId
    roleDefinitionId: searchIndexDataContributorRoleId
  }
}

resource deployerArchiveContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployArchive) {
  name: guid(documentContainer!.id, deploymentPrincipalId, storageBlobDataContributorRoleId)
  scope: documentContainer!
  properties: {
    principalId: deploymentPrincipalId
    roleDefinitionId: storageBlobDataContributorRoleId
  }
}

resource searchModelUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryAccount.id, searchService.name, cognitiveServicesUserRoleId)
  scope: foundryAccount
  properties: {
    principalId: searchService.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: cognitiveServicesUserRoleId
  }
}

module connection 'modules/foundry-connection.bicep' = {
  name: 'hotel-iq-search-connection'
  params: {
    foundryAccountName: foundryAccountName
    foundryProjectName: foundryProjectName
    searchConnectionName: searchConnectionName
    searchServiceEndpoint: 'https://${searchService.name}.search.windows.net'
    searchServiceId: searchService.id
    searchServiceLocation: searchLocation
  }
}

output searchServiceEndpoint string = 'https://${searchService.name}.search.windows.net'
output searchServiceId string = searchService.id
output searchServicePrincipalId string = searchService.identity.principalId
output storageAccountName string = storageAccountName
output storageAccountUrl string = deployArchive
  ? storageAccount!.properties.primaryEndpoints.blob
  : existingArchive.properties.primaryEndpoints.blob
output documentContainerName string = 'hotel-docs'
output searchConnectionName string = connection.outputs.searchConnectionName
