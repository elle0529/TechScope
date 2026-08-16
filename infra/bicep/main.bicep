targetScope = 'subscription'

@description('Deployment region.')
param location string

@description('Environment name.')
@allowed([
  'dev'
  'test'
  'prod'
])
param environment string = 'dev'

@description('Project name.')
param projectName string = 'techscope'

@description('Stable short suffix chosen by automation.')
@minLength(4)
@maxLength(8)
param suffix string

var compact = toLower(replace('${projectName}${environment}${suffix}', '-', ''))
var shortPrefix = toLower('${projectName}-${environment}-${suffix}')

output resourceGroupName string = 'rg-${shortPrefix}'
output storageAccountName string = take('${compact}dl', 24)
output dataFactoryName string = '${shortPrefix}-adf'
output databricksWorkspaceName string = '${shortPrefix}-dbw'
output sqlServerName string = '${shortPrefix}-sql'
output searchServiceName string = '${shortPrefix}-search'
output openAIAccountName string = '${shortPrefix}-aoai'
output cosmosAccountName string = '${shortPrefix}-cosmos'
output analysisServicesName string = take(replace('${compact}aas', '-', ''), 63)
output location string = location
output environment string = environment
