targetScope = 'resourceGroup'

param location string
param project string
param env string
param suffix string
param sqlAdminLogin string

@secure()
param sqlAdminPassword string

var compact = toLower(replace('${project}${env}${suffix}', '-', ''))
var storageName = take('st${compact}', 24)
var adfName = 'adf-${project}-${env}-${suffix}'
var dbwName = 'dbw-${project}-${env}-${suffix}'
var dbwManagedResourceGroupName = 'rg-${project}-${env}-dbw-managed-${suffix}'
var sqlServerName = 'sql-${project}-${env}-${suffix}'
var sqlDatabaseName = 'sqldb-${project}-${env}'
var fileSystemName = 'techscope'
var storageBlobDataContributorRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
)

resource storage 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Enabled'
    accessTier: 'Hot'
  }
  tags: {
    project: 'TechScope'
    environment: env
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = {
  parent: storage
  name: 'default'
  properties: {}
}

resource fileSystem 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: fileSystemName
  properties: {
    publicAccess: 'None'
  }
}

resource factory 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: adfName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    project: 'TechScope'
    environment: env
  }
}

resource adfStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, factory.id, storageBlobDataContributorRoleDefinitionId)
  scope: storage
  properties: {
    roleDefinitionId: storageBlobDataContributorRoleDefinitionId
    principalId: factory.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource linkedService 'Microsoft.DataFactory/factories/linkedservices@2018-06-01' = {
  parent: factory
  name: 'LS_ADLS_TechScope'
  properties: {
    type: 'AzureBlobFS'
    typeProperties: {
      url: storage.properties.primaryEndpoints.dfs
      authentication: 'MSI'
    }
    annotations: [
      'TechScope'
      'P1D'
    ]
  }
}

resource landingDataset 'Microsoft.DataFactory/factories/datasets@2018-06-01' = {
  parent: factory
  name: 'DS_CSV_Landing'
  properties: {
    linkedServiceName: {
      referenceName: linkedService.name
      type: 'LinkedServiceReference'
    }
    parameters: {
      folder_name: {
        type: 'String'
      }
      file_name: {
        type: 'String'
      }
    }
    type: 'DelimitedText'
    typeProperties: {
      location: {
        type: 'AzureBlobFSLocation'
        fileName: {
          value: '@dataset().file_name'
          type: 'Expression'
        }
        folderPath: {
          value: '@dataset().folder_name'
          type: 'Expression'
        }
        fileSystem: fileSystemName
      }
      columnDelimiter: ','
      escapeChar: '\\'
      firstRowAsHeader: true
      quoteChar: '"'
    }
    schema: []
  }
}

resource bronzeDataset 'Microsoft.DataFactory/factories/datasets@2018-06-01' = {
  parent: factory
  name: 'DS_CSV_Bronze'
  properties: {
    linkedServiceName: {
      referenceName: linkedService.name
      type: 'LinkedServiceReference'
    }
    parameters: {
      folder_name: {
        type: 'String'
      }
      file_name: {
        type: 'String'
      }
    }
    type: 'DelimitedText'
    typeProperties: {
      location: {
        type: 'AzureBlobFSLocation'
        fileName: {
          value: '@dataset().file_name'
          type: 'Expression'
        }
        folderPath: {
          value: '@dataset().folder_name'
          type: 'Expression'
        }
        fileSystem: fileSystemName
      }
      columnDelimiter: ','
      escapeChar: '\\'
      firstRowAsHeader: true
      quoteChar: '"'
    }
    schema: []
  }
}

resource pipeline 'Microsoft.DataFactory/factories/pipelines@2018-06-01' = {
  parent: factory
  name: 'PL_Ingest_TechScope'
  properties: {
    parameters: {
      structured_folder: {
        type: 'String'
        defaultValue: 'landing/structured'
      }
      file_list: {
        type: 'Array'
        defaultValue: [
          'technology.csv'
          'category.csv'
          'relation.csv'
          'company_usecase.csv'
          'architecture_mapping.csv'
        ]
      }
    }
    activities: [
      {
        name: 'Get Structured Metadata'
        type: 'GetMetadata'
        dependsOn: []
        policy: {
          timeout: '0.00:05:00'
          retry: 2
          retryIntervalInSeconds: 15
          secureOutput: false
          secureInput: false
        }
        typeProperties: {
          dataset: {
            referenceName: landingDataset.name
            type: 'DatasetReference'
            parameters: {
              folder_name: {
                value: '@pipeline().parameters.structured_folder'
                type: 'Expression'
              }
              file_name: 'technology.csv'
            }
          }
          fieldList: [
            'exists'
            'size'
            'lastModified'
          ]
        }
      }
      {
        name: 'ForEach Structured File'
        type: 'ForEach'
        dependsOn: [
          {
            activity: 'Get Structured Metadata'
            dependencyConditions: [
              'Succeeded'
            ]
          }
        ]
        typeProperties: {
          items: {
            value: '@pipeline().parameters.file_list'
            type: 'Expression'
          }
          isSequential: false
          batchCount: 5
          activities: [
            {
              name: 'Copy Structured CSV To Bronze'
              type: 'Copy'
              dependsOn: []
              policy: {
                timeout: '0.00:10:00'
                retry: 2
                retryIntervalInSeconds: 15
                secureOutput: false
                secureInput: false
              }
              typeProperties: {
                source: {
                  type: 'DelimitedTextSource'
                  storeSettings: {
                    type: 'AzureBlobFSReadSettings'
                    recursive: false
                    enablePartitionDiscovery: false
                  }
                  formatSettings: {
                    type: 'DelimitedTextReadSettings'
                  }
                }
                sink: {
                  type: 'DelimitedTextSink'
                  storeSettings: {
                    type: 'AzureBlobFSWriteSettings'
                    copyBehavior: 'PreserveHierarchy'
                  }
                  formatSettings: {
                    type: 'DelimitedTextWriteSettings'
                    quoteAllText: true
                    fileExtension: '.csv'
                  }
                }
                enableStaging: false
                translator: {
                  type: 'TabularTranslator'
                  typeConversion: true
                  typeConversionSettings: {
                    allowDataTruncation: false
                    treatBooleanAsNumber: false
                  }
                }
              }
              inputs: [
                {
                  referenceName: landingDataset.name
                  type: 'DatasetReference'
                  parameters: {
                    folder_name: {
                      value: '@pipeline().parameters.structured_folder'
                      type: 'Expression'
                    }
                    file_name: {
                      value: '@item()'
                      type: 'Expression'
                    }
                  }
                }
              ]
              outputs: [
                {
                  referenceName: bronzeDataset.name
                  type: 'DatasetReference'
                  parameters: {
                    folder_name: {
                      value: '@concat(\'bronze/\', replace(item(), \'.csv\', \'\'), \'/\', formatDateTime(utcnow(),\'yyyy/MM/dd\'))'
                      type: 'Expression'
                    }
                    file_name: {
                      value: '@item()'
                      type: 'Expression'
                    }
                  }
                }
              ]
            }
          ]
        }
      }
    ]
    annotations: [
      'TechScope'
      'P1D'
    ]
  }
  dependsOn: [
    adfStorageRole
  ]
}

resource databricks 'Microsoft.Databricks/workspaces@2024-05-01' = {
  name: dbwName
  location: location
  sku: {
    name: 'premium'
  }
  properties: {
    managedResourceGroupId: subscriptionResourceId(
      'Microsoft.Resources/resourceGroups',
      dbwManagedResourceGroupName
    )
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    project: 'TechScope'
    environment: env
  }
}

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: sqlServerName
  location: location
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    version: '12.0'
  }
  tags: {
    project: 'TechScope'
    environment: env
  }
}

resource azureServicesFirewall 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: sqlDatabaseName
  location: location
  sku: {
    name: 'Basic'
    tier: 'Basic'
    capacity: 5
  }
  properties: {
    maxSizeBytes: 2147483648
    zoneRedundant: false
  }
}

output storageAccountName string = storage.name
output storageDfsEndpoint string = storage.properties.primaryEndpoints.dfs
output fileSystemName string = fileSystem.name
output dataFactoryName string = factory.name
output databricksWorkspaceName string = databricks.name
output databricksWorkspaceUrl string = databricks.properties.workspaceUrl
output databricksWorkspaceResourceId string = databricks.id
output sqlServerName string = sqlServer.name
output sqlServerFqdn string = '${sqlServer.name}.database.windows.net'
output sqlDatabaseName string = sqlDatabase.name
