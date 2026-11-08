@description('Tenant-local capacity name; use an existing approved capacity instead when available.')
param capacityName string

@description('Azure region for the capacity.')
param location string

@description('Tenant-local UPNs for capacity administrators.')
param administrators array

@allowed([
  'dev'
  'test'
  'prod'
])
param environmentName string

@allowed([
  'F2'
  'F4'
  'F8'
  'F16'
])
@description('Start with the smallest adequate SKU and scale only after measuring workload needs.')
param skuName string = 'F2'

resource capacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: capacityName
  location: location
  tags: {
    environment: environmentName
    workload: 'hotel-agent'
  }
  sku: {
    name: skuName
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: administrators
    }
  }
}

output capacityResourceId string = capacity.id
