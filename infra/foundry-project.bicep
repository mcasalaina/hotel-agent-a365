targetScope = 'resourceGroup'

@description('Azure region for the new Foundry account and project.')
param location string

@description('Globally unique Foundry account name and custom subdomain.')
param accountName string

@description('Name of the new Foundry project.')
param projectName string

@description('Model deployment capacity; verify regional subscription quota before deployment.')
@minValue(1)
param modelCapacity int

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
    description: 'Hotel guest-services agent with Fabric, Foundry IQ, Work IQ, and Agent 365.'
  }
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: 'gpt-5.4-mini'
  dependsOn: [
    project
  ]
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4-mini'
      version: '2026-03-17'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

var cognitiveServicesUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'a97b65f3-24c7-4388-baec-2e87135dc908'
)

resource projectModelAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, project.id, cognitiveServicesUserRoleId)
  scope: account
  properties: {
    principalId: project.identity.principalId!
    principalType: 'ServicePrincipal'
    roleDefinitionId: cognitiveServicesUserRoleId
  }
}

output accountId string = account.id
output projectId string = project.id
output projectPrincipalId string = project.identity.principalId!
output modelDeploymentName string = model.name
