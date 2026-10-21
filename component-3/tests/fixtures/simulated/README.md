# Simulated integration fixtures

Every file here is **SIMULATED**. These fixtures are not approved Component 1
or Component 2 contracts, and their reference values are not authentic client
approval or validation evidence.

- `valid_input_package.json` is the assumed C1/C2 contract version `1.0` happy
  path used to test normalization and identity preservation. Its
  `UML-CLASS-001` source uses only the documented limited PlantUML subset.
- `invalid_input_scenarios.json` contains named mutations applied to the valid
  fixture to exercise each deterministic rejection rule.
- `malformed_input.json` is intentionally invalid JSON for the HTTP 422 test.
- `task_management_input_package.json` is the explicitly simulated Task 6
  input for the narrow Task Management MVP. Its approval and validation
  references remain unauthenticated labels rather than upstream proof.
- `student_management_input_package.json`,
  `library_management_input_package.json`, and
  `inventory_management_input_package.json` are explicitly simulated Stage 1
  dynamic-CRUD inputs. They exercise one shared generator; they are not actual
  C1/C2 packages or evidence of completed upstream integration.
- `researcher_curated_traceability_ground_truth.json` contains manually
  authored, simulated Task 7 link labels for evaluation-method tests. It is
  a unit-test oracle whose independent human-review status is `NOT_VERIFIED`;
  it is not Component 4 output, production evidence, or a benchmark result.

- `scoped_regeneration/c4_defect_scenarios.json` holds eight SIMULATED
  Component 4 defect scenarios for Task 9. Expected modules and statuses are
  implementer-authored labels with review status `NOT_INDEPENDENTLY_REVIEWED`;
  they check the impact-selection method and are not Component 4 output or a
  benchmark. `buggy_task_service.js` is a deliberately defective baseline
  service and `repaired_task_service.js` is the deterministic mock "model"
  response; neither is real model output.

The mutation format is test-only scaffolding designed to keep assumptions
centralized and easy to revise when the C1 and C2 owners provide real schemas.
