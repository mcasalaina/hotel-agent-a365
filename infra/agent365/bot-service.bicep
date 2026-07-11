@description('Globally unique Azure Bot Service resource name.')
param botName string

@description('Customer-facing bot display name.')
param displayName string

@description('Microsoft Entra client ID of the Foundry managed agent identity blueprint.')
param blueprintClientId string

@description('Microsoft Entra tenant ID.')
param tenantId string

@description('Foundry Hosted Agent activity protocol endpoint.')
param endpoint string

@allowed([
  'F0'
  'S1'
])
@description('Azure Bot Service pricing tier.')
param botServiceSku string = 'F0'

resource botService 'Microsoft.BotService/botServices@2022-09-15' = {
  name: botName
  kind: 'azurebot'
  location: 'global'
  sku: {
    name: botServiceSku
  }
  properties: {
    displayName: displayName
    endpoint: endpoint
    msaAppId: blueprintClientId
    msaAppTenantId: tenantId
    msaAppType: 'SingleTenant'
    publicNetworkAccess: 'Enabled'
  }
}

resource teamsChannel 'Microsoft.BotService/botServices/channels@2021-03-01' = {
  parent: botService
  location: 'global'
  name: 'MsTeamsChannel'
  properties: {
    channelName: 'MsTeamsChannel'
  }
}

output botServiceArmId string = botService.id
output messagingEndpoint string = endpoint
