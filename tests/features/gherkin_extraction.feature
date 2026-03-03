Feature: Gherkin Extraction
  As the jira-connector
  I want to detect and extract Gherkin scenarios from Jira issue descriptions
  So that AI agents implement against specific acceptance criteria

  Scenario: Single Feature block extracted
    Given a Jira issue description containing one Feature block
    When Gherkin extraction runs
    Then one .feature file should be created
    And it should contain the Feature name and Scenario

  Scenario: Multiple Feature blocks extracted
    Given a Jira issue description containing two Feature blocks
    When Gherkin extraction runs
    Then two .feature files should be created
    And each should be named after its Feature

  Scenario: No Gherkin in description
    Given a Jira issue description with no Gherkin keywords
    When Gherkin extraction runs
    Then no .feature files should be created

  Scenario: Feature files uploaded with job
    Given Gherkin scenarios were extracted
    When the Crew job is created
    Then the .feature files should be uploaded as documents
    And Crew Studio's feature_parser should find them
