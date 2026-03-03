Feature: Status Synchronization
  As the jira-connector
  I want to poll Crew job status and update Jira
  So that stakeholders see progress without leaving Jira

  Scenario: Job completes successfully
    Given a Crew job exists for issue "PROJ-20"
    And the job status changes to "completed"
    When the status poller runs
    Then a Jira comment "completed" should be posted
    And the Jira issue should transition to "Done"
    And the mapping should be marked as done

  Scenario: Job fails
    Given a Crew job exists for issue "PROJ-21"
    And the job status changes to "failed" with error "Build error"
    When the status poller runs
    Then a Jira comment "failed" should be posted
    And the Jira issue should transition to "Failed"
    And the mapping should be marked as done

  Scenario: Job still running
    Given a Crew job exists for issue "PROJ-22"
    And the job status is "running"
    When the status poller runs
    Then no transition should occur
    And the mapping should remain active
