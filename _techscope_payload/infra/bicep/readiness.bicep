targetScope = 'subscription'

@description('Readiness validation region.')
param location string

@description('Temporary name used only by ARM validation. This template is never deployed by the readiness probe.')
param validationResourceGroupName string

resource validationRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: validationResourceGroupName
  location: location
}

output validationResourceGroupName string = validationRg.name
