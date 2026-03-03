Feature: Jira Webhook Processing
  As the jira-connector service
  I want to process Jira webhooks and create Crew jobs
  So that Jira issues are automatically developed by AI agents

  Scenario: Greenfield build from Story issue
    Given a Jira webhook for issue "PROJ-10" with type "Story"
    And the issue summary is "Create a new REST API for inventory"
    And the issue description has no repository URL
    When the webhook is received
    Then the AI classifier should return mode "build"
    And a Crew job should be created with mode "build"
    And no github_urls should be passed
    And a Jira comment "Crew job started" should be posted

  Scenario: Refactor from Bug issue with repo URL
    Given a Jira webhook for issue "PROJ-12" with type "Bug"
    And the issue description contains "Fix NPE in https://github.com/acme/backend"
    When the webhook is received
    Then the AI classifier should return mode "refactor"
    And a Crew job should be created with mode "refactor"
    And github_urls should contain "https://github.com/acme/backend"
    And POST /api/jobs/<id>/refactor should be called

  Scenario: Issue with Gherkin acceptance criteria
    Given a Jira webhook for issue "PROJ-14" with type "Story"
    And the issue description contains Gherkin scenarios
    When the webhook is received
    Then .feature files should be extracted and uploaded
    And a Crew job should be created with the feature files attached

  Scenario: Duplicate webhook is ignored
    Given a Crew job is already running for issue "PROJ-10"
    When a duplicate webhook is received for "PROJ-10"
    Then no new job should be created
    And the webhook should return 200 OK
