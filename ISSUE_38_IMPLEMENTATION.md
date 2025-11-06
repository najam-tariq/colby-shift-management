# Issue #38 Implementation: Undesirable Time Windows

## User Story
As an ITS supervisor, I want to define which time windows count as "undesirable" (early morning, late evening, or weekends) so the system knows what to balance.

## Implementation Summary

### Features Implemented
- Interface to define undesirable time ranges at `/constraints/undesirable-windows`
- Support for multiple undesirable windows per policy
- Weight system (0.1 to 10.0) for different undesirable types
- Database persistence with full CRUD operations

### Database Changes
- Added `UndesirableTimeWindow` model with fields:
  - `window_id`, `policy_id`, `name`, `day_of_week`, `start_time`, `end_time`, `weight`, `window_type`
- Updated `Policy` model with `undesirable_windows` relationship

### Files Modified/Created
- `models.py` - Added UndesirableTimeWindow model
- `blueprints/constraints/routes.py` - Added window management routes
- `blueprints/constraints/templates/constraints_index.html` - Added navigation
- `blueprints/constraints/templates/undesirable_windows.html` - Main interface
- `blueprints/constraints/templates/add_undesirable_window.html` - Add form
- `blueprints/auth/templates/landing.html` - Updated navigation

### Routes Added
- `GET /constraints/undesirable-windows` - List windows
- `GET/POST /constraints/undesirable-windows/add` - Add new window
- `POST /constraints/undesirable-windows/delete/<id>` - Delete window

**Status**: COMPLETE - All acceptance criteria implemented and tested.