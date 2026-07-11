targetScope = 'resourceGroup'

@description('Azure region for the supporting resources.')
param location string

@description('Globally unique Azure AI Search service name.')
param searchServiceName string

@description('Globally unique StorageV2 account name.')
param storageAccountName string

@description('Object ID of the existing Foundry project managed identity.')
param foundryProjectPrincipalId string

@description('Object ID of the principal running azd.')
param deploymentPrincipalId string

@description('Tags applied to supporting resources.')
param tags object = {}

var searchServiceContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
)
var searchIndexDataContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
)
var storageBlobDataReaderRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
)
var storageBlobDataContributorRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
)

resource searchService 'Microsoft.Search/searchServices@2025-05-01' = {
  name: searchServiceName
  location: location
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

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-06-01' = {
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

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-06-01' = {
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

resource documentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobService
  name: 'hotel-docs'
  properties: {
    publicAccess: 'None'
  }
}

resource projectSearchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, foundryProjectPrincipalId, searchServiceContributorRoleId)
  scope: searchService
  properties: {
    principalId: foundryProjectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: searchServiceContributorRoleId
  }
}

resource projectSearchIndexDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, foundryProjectPrincipalId, searchIndexDataContributorRoleId)
  scope: searchService
  properties: {
    principalId: foundryProjectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: searchIndexDataContributorRoleId
  }
}

resource projectBlobDataReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, foundryProjectPrincipalId, storageBlobDataReaderRoleId)
  scope: storageAccount
  properties: {
    principalId: foundryProjectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: storageBlobDataReaderRoleId
  }
}

resource searchBlobDataReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, searchService.name, storageBlobDataReaderRoleId)
  scope: storageAccount
  properties: {
    principalId: searchService.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: storageBlobDataReaderRoleId
  }
}

resource deployerSearchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, deploymentPrincipalId, searchServiceContributorRoleId)
  scope: searchService
  properties: {
    principalId: deploymentPrincipalId
    roleDefinitionId: searchServiceContributorRoleId
  }
}

resource deployerSearchIndexDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, deploymentPrincipalId, searchIndexDataContributorRoleId)
  scope: searchService
  properties: {
    principalId: deploymentPrincipalId
    roleDefinitionId: searchIndexDataContributorRoleId
  }
}

resource deployerBlobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, deploymentPrincipalId, storageBlobDataContributorRoleId)
  scope: storageAccount
  properties: {
    principalId: deploymentPrincipalId
    roleDefinitionId: storageBlobDataContributorRoleId
  }
}

output searchServiceEndpoint string = 'https://${searchService.name}.search.windows.net'
output searchServiceId string = searchService.id
output searchServiceName string = searchService.name
output storageAccountName string = storageAccount.name
output documentContainerName string = documentContainer.name
