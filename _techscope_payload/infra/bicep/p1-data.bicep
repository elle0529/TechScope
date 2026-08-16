targetScope = 'subscription'

@description('Preferred Azure region selected by preflight.')
param location string

param project string = 'techscope'
param env string = 'dev'

@minLength(6)
@maxLength(10)
param suffix string

param sqlAdminLogin string

@secure()
param sqlAdminPassword string

var resourceGroupName = 'rg-${project}-${env}-${suffix}'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: {
    project: 'TechScope'
    environment: env
    managedBy: 'TechScope-P1D'
  }
}

module data './p1-data-rg.bicep' = {
  name: 'techscope-p1-data-${suffix}'
  scope: rg
  params: {
    location: location
    project: project
    env: env
    suffix: suffix
    sqlAdminLogin: sqlAdminLogin
    sqlAdminPassword: sqlAdminPassword
  }
}

output resourceGroupName string = rg.name
output location string = location
output storageAccountName string = data.outputs.storageAccountName
output storageDfsEndpoint string = data.outputs.storageDfsEndpoint
output fileSystemName string = data.outputs.fileSystemName
output dataFactoryName string = data.outputs.dataFactoryName
output databricksWorkspaceName string = data.outputs.databricksWorkspaceName
output databricksWorkspaceUrl string = data.outputs.databricksWorkspaceUrl
output databricksWorkspaceResourceId string = data.outputs.databricksWorkspaceResourceId
output sqlServerName string = data.outputs.sqlServerName
output sqlServerFqdn string = data.outputs.sqlServerFqdn
output sqlDatabaseName string = data.outputs.sqlDatabaseName
