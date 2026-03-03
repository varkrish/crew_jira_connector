Feature: Input Validation
  As the jira-connector service
  I want to validate Jira issue content before creating Crew jobs
  So that invalid or malicious input is rejected early

  Scenario: Empty description is rejected
    Given a Jira webhook for issue "PROJ-50"
    And the issue summary is "fix"
    And the issue description is empty
    When the webhook is received
    Then no Crew job should be created
    And a Jira comment should say "issue description is empty or too short"

  Scenario: Invalid repo URL is rejected
    Given a Jira webhook for issue "PROJ-51"
    And the description contains "See http://localhost:8080/admin"
    When the webhook is received
    Then no Crew job should be created
    And a Jira comment should say "Invalid repository URL"

  Scenario: Non-git host URL is rejected
    Given a Jira webhook for issue "PROJ-52"
    And the description contains "See https://docs.google.com/spreadsheet/xyz"
    When the webhook is received
    Then the URL should not be treated as a repo URL
    And the AI classifier should classify based on text only

  Scenario: Inaccessible repo is rejected
    Given a Jira webhook for issue "PROJ-53"
    And the description contains "Fix bug in https://github.com/nonexistent/repo-404"
    And VALIDATE_REPO_ACCESS is enabled
    When the webhook is received
    Then no Crew job should be created
    And a Jira comment should say "Repository not found or not accessible"

  Scenario: Refactor without repo URL is rejected
    Given a Jira webhook for issue "PROJ-54"
    And the AI classifier returns mode "refactor" with no repo_url
    When classifier output validation runs
    Then no Crew job should be created
    And a Jira comment should say "Refactor requires a repository URL"

  Scenario: Valid issue passes all checks
    Given a Jira webhook for issue "PROJ-55"
    And the summary is "Add user search endpoint"
    And the description is "Implement GET /api/users/search with query params. Repo: https://github.com/acme/backend"
    When the webhook is received
    Then all validation stages should pass
    And a Crew job should be created
