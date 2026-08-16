SET NOCOUNT ON;
SET XACT_ABORT ON;
IF SCHEMA_ID(N'techscope') IS NULL EXEC(N'CREATE SCHEMA techscope AUTHORIZATION dbo;');

IF OBJECT_ID(N'techscope.DimTechnology',N'U') IS NULL
CREATE TABLE techscope.DimTechnology(
 TechnologyKey bigint IDENTITY(1,1) PRIMARY KEY,
 TechnologyId varchar(16) NOT NULL UNIQUE,
 TechnologyName nvarchar(256) NOT NULL,
 CategoryId varchar(16) NULL,
 CategoryName nvarchar(256) NULL,
 SourceId varchar(16) NOT NULL,
 LoadedAtUtc datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

IF OBJECT_ID(N'techscope.DimCategory',N'U') IS NULL
CREATE TABLE techscope.DimCategory(
 CategoryKey bigint IDENTITY(1,1) PRIMARY KEY,
 CategoryId varchar(16) NOT NULL UNIQUE,
 CategoryName nvarchar(256) NOT NULL,
 SourceId varchar(16) NOT NULL,
 LoadedAtUtc datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

IF OBJECT_ID(N'techscope.DimCompany',N'U') IS NULL
CREATE TABLE techscope.DimCompany(
 CompanyKey bigint IDENTITY(1,1) PRIMARY KEY,
 CompanyId varchar(16) NOT NULL UNIQUE,
 CompanyName nvarchar(256) NOT NULL,
 Industry nvarchar(256) NULL,
 SourceId varchar(16) NULL,
 LoadedAtUtc datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

IF OBJECT_ID(N'techscope.DimArchitecture',N'U') IS NULL
CREATE TABLE techscope.DimArchitecture(
 ArchitectureKey bigint IDENTITY(1,1) PRIMARY KEY,
 LayerCode varchar(8) NOT NULL UNIQUE,
 LayerName nvarchar(128) NOT NULL,
 LoadedAtUtc datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

IF OBJECT_ID(N'techscope.FactTechnologyRelation',N'U') IS NULL
BEGIN
 CREATE TABLE techscope.FactTechnologyRelation(
  TechnologyRelationKey bigint IDENTITY(1,1) PRIMARY KEY,
  SourceTechnologyId varchar(16) NOT NULL,
  TargetTechnologyId varchar(16) NOT NULL,
  RelationType nvarchar(128) NOT NULL,
  EvidenceType varchar(32) NOT NULL,
  SourceId varchar(16) NOT NULL,
  LoadedAtUtc datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
  FOREIGN KEY(SourceTechnologyId) REFERENCES techscope.DimTechnology(TechnologyId),
  FOREIGN KEY(TargetTechnologyId) REFERENCES techscope.DimTechnology(TechnologyId)
 );
 CREATE INDEX IX_FTR_Source ON techscope.FactTechnologyRelation(SourceTechnologyId);
 CREATE INDEX IX_FTR_Target ON techscope.FactTechnologyRelation(TargetTechnologyId);
END;

IF OBJECT_ID(N'techscope.FactCompanyTechnology',N'U') IS NULL
BEGIN
 CREATE TABLE techscope.FactCompanyTechnology(
  CompanyTechnologyKey bigint IDENTITY(1,1) PRIMARY KEY,
  CompanyId varchar(16) NOT NULL,
  TechnologyId varchar(16) NOT NULL,
  UseCase nvarchar(1000) NULL,
  BusinessEffect nvarchar(1000) NULL,
  EvidenceType varchar(32) NULL,
  SourceId varchar(16) NULL,
  LoadedAtUtc datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
  FOREIGN KEY(CompanyId) REFERENCES techscope.DimCompany(CompanyId),
  FOREIGN KEY(TechnologyId) REFERENCES techscope.DimTechnology(TechnologyId)
 );
 CREATE INDEX IX_FCT_Company ON techscope.FactCompanyTechnology(CompanyId);
 CREATE INDEX IX_FCT_Technology ON techscope.FactCompanyTechnology(TechnologyId);
END;

IF OBJECT_ID(N'techscope.FactAIInteraction',N'U') IS NULL
CREATE TABLE techscope.FactAIInteraction(
 AIInteractionKey bigint IDENTITY(1,1) PRIMARY KEY,
 InteractionId uniqueidentifier NOT NULL UNIQUE,
 OccurredAtUtc datetime2(3) NOT NULL,
 QuestionLength int NULL,
 RetrievedChunkCount int NULL,
 AnswerGrounded bit NULL,
 ResponseLatencyMs int NULL,
 FeedbackScore tinyint NULL,
 SourceId varchar(16) NULL
);
GO

CREATE OR ALTER VIEW techscope.vwTechnologyOverview AS
SELECT t.TechnologyId,t.TechnologyName,t.CategoryId,t.CategoryName,t.SourceId,
 COUNT(DISTINCT otr.TechnologyRelationKey) OutgoingRelationCount,
 COUNT(DISTINCT itr.TechnologyRelationKey) IncomingRelationCount,
 COUNT(DISTINCT fct.CompanyId) CompanyCount
FROM techscope.DimTechnology t
LEFT JOIN techscope.FactTechnologyRelation otr ON otr.SourceTechnologyId=t.TechnologyId
LEFT JOIN techscope.FactTechnologyRelation itr ON itr.TargetTechnologyId=t.TechnologyId
LEFT JOIN techscope.FactCompanyTechnology fct ON fct.TechnologyId=t.TechnologyId
GROUP BY t.TechnologyId,t.TechnologyName,t.CategoryId,t.CategoryName,t.SourceId;
GO

CREATE OR ALTER VIEW techscope.vwCategorySummary AS
SELECT c.CategoryId,c.CategoryName,COUNT(DISTINCT t.TechnologyId) TechnologyCount
FROM techscope.DimCategory c
LEFT JOIN techscope.DimTechnology t ON t.CategoryId=c.CategoryId
GROUP BY c.CategoryId,c.CategoryName;
GO

CREATE OR ALTER VIEW techscope.vwAIInteractionSummary AS
SELECT CAST(OccurredAtUtc AS date) InteractionDate,
 COUNT_BIG(*) InteractionCount,
 SUM(CASE WHEN AnswerGrounded=1 THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) GroundedCount,
 AVG(CONVERT(decimal(18,2),ResponseLatencyMs)) AvgLatencyMs,
 AVG(CONVERT(decimal(18,2),FeedbackScore)) AvgFeedbackScore
FROM techscope.FactAIInteraction
GROUP BY CAST(OccurredAtUtc AS date);
GO
