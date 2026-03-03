Feature: AI-Based Mode Detection
  As the jira-connector
  I want to use an LLM to classify Jira issues
  So that I pick the correct Crew Studio mode without custom Jira fields

  Scenario: LLM classifies a new feature request as build
    Given a Jira issue with summary "Create a payment microservice"
    And description "We need a new service to handle Stripe payments"
    When the AI classifier runs
    Then the mode should be "build"
    And confidence should be above 0.7

  Scenario: LLM classifies a bug fix as refactor
    Given a Jira issue with summary "Fix login timeout issue"
    And description "Users report timeouts at https://github.com/acme/auth-service"
    When the AI classifier runs
    Then the mode should be "refactor"
    And repo_url should be "https://github.com/acme/auth-service"

  Scenario: LLM is unavailable, fallback to heuristic
    Given the LLM endpoint is unreachable
    And a Jira issue with a GitHub URL in the description
    When the AI classifier runs
    Then the fallback should return mode "refactor"
    And a warning should be logged

  Scenario: LLM returns low confidence
    Given a Jira issue with ambiguous description "Update the system"
    When the AI classifier runs
    And confidence is below the threshold
    Then the fallback mode should be used
