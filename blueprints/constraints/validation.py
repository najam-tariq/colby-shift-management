"""
Shift Duration Validation Utilities for Issue #26 & #27
Provides validation logic for schedule generators and manual shift editing
Includes automatic rejection system for impractical shifts
"""

from datetime import datetime, timedelta, time as dt_time
from typing import Tuple, Optional, List, Dict
from models import Policy, Shift, RejectedShift, SplitShift, db
import uuid

class ShiftValidationError(Exception):
    """Custom exception for shift validation errors"""
    pass

class AutomaticRejectionSystem:
    """
    Automatic shift rejection system for schedule generation (Issue #27)
    Prevents impractical shifts from being created and logs rejections
    """
    
    @staticmethod
    def reject_and_log_shift(term_id: int, user_id: int, start_time: dt_time, 
                           end_time: dt_time, shift_date, reason: str, 
                           rejection_type: str, session_id: str = None) -> None:
        """
        Log a rejected shift attempt for debugging (Issue #27)
        
        Args:
            term_id: Term ID
            user_id: User ID (can be None during generation)
            start_time: Proposed start time
            end_time: Proposed end time
            shift_date: Proposed date
            reason: Rejection reason
            rejection_type: Type of rejection ('duration', 'policy', 'coverage')
            session_id: Generation session ID for grouping
        """
        duration = DurationValidator.get_duration_minutes(start_time, end_time)
        
        rejection = RejectedShift(
            term_id=term_id,
            user_id=user_id,
            proposed_start_time=start_time,
            proposed_end_time=end_time,
            proposed_date=shift_date,
            duration_minutes=duration,
            rejection_reason=reason,
            rejection_type=rejection_type,
            schedule_generation_session=session_id or str(uuid.uuid4())
        )
        
        db.session.add(rejection)
        db.session.commit()
    
    @staticmethod
    def auto_reject_short_shifts(term_id: int, proposed_shifts: List[Dict], 
                               session_id: str = None) -> Tuple[List[Dict], List[Dict], bool]:
        """
        Automatically reject shifts shorter than 1 hour during generation (Issue #27)
        
        Args:
            term_id: Term ID to get policy for
            proposed_shifts: List of shift dictionaries with start_time, end_time, etc.
            session_id: Generation session ID
            
        Returns:
            Tuple of (valid_shifts, rejected_shifts, coverage_warning)
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
            
        policy = Policy.get_policy_for_term(term_id)
        if not policy:
            raise ShiftValidationError(f"No policy found for term {term_id}")
        
        valid_shifts = []
        rejected_shifts = []
        coverage_gaps = []
        
        for shift_data in proposed_shifts:
            duration = DurationValidator.get_duration_minutes(
                shift_data['start_time'], 
                shift_data['end_time']
            )
            
            # Automatic rejection for shifts shorter than policy minimum
            if duration < policy.min_shift_length:
                rejection_reason = (f"Automatic rejection: {duration} minutes below "
                                  f"minimum {policy.min_shift_length} minutes")
                
                # Log the rejection
                AutomaticRejectionSystem.reject_and_log_shift(
                    term_id=term_id,
                    user_id=shift_data.get('user_id'),
                    start_time=shift_data['start_time'],
                    end_time=shift_data['end_time'],
                    shift_date=shift_data['date'],
                    reason=rejection_reason,
                    rejection_type='duration',
                    session_id=session_id
                )
                
                rejected_shifts.append({
                    **shift_data,
                    'rejection_reason': rejection_reason,
                    'duration_minutes': duration
                })
                
                # Track potential coverage gap
                coverage_gaps.append(shift_data)
                
            else:
                valid_shifts.append(shift_data)
        
        # Check for coverage warnings
        coverage_warning = len(coverage_gaps) > 0
        
        return valid_shifts, rejected_shifts, coverage_warning
    
    @staticmethod
    def get_rejection_stats(term_id: int, session_id: str = None) -> Dict:
        """
        Get statistics about rejected shifts for a term or session
        
        Args:
            term_id: Term ID
            session_id: Optional session ID to filter by
            
        Returns:
            Dictionary with rejection statistics
        """
        query = RejectedShift.query.filter_by(term_id=term_id)
        
        if session_id:
            query = query.filter_by(schedule_generation_session=session_id)
            
        rejections = query.all()
        
        if not rejections:
            return {
                'total_rejections': 0,
                'duration_rejections': 0,
                'avg_rejected_duration': 0,
                'shortest_rejected': 0,
                'most_recent': None
            }
        
        duration_rejections = [r for r in rejections if r.rejection_type == 'duration']
        durations = [r.duration_minutes for r in rejections]
        
        return {
            'total_rejections': len(rejections),
            'duration_rejections': len(duration_rejections),
            'avg_rejected_duration': sum(durations) / len(durations),
            'shortest_rejected': min(durations),
            'longest_rejected': max(durations),
            'most_recent': max(rejections, key=lambda r: r.created_at).created_at,
            'session_id': session_id
        }

class AutomaticSplitSystem:
    """
    Automatic shift splitting system for schedule generation (Issue #28)
    Splits long shifts into compliant chunks with proper breaks
    """
    
    @staticmethod
    def split_and_log_shift(term_id: int, user_id: int, start_time: dt_time, 
                          end_time: dt_time, shift_date, session_id: str = None) -> List[Dict]:
        """
        Split a long shift and log the operation (Issue #28)
        
        Args:
            term_id: Term ID
            user_id: User ID (can be None during generation)
            start_time: Original start time
            end_time: Original end time
            shift_date: Shift date
            session_id: Generation session ID for grouping
            
        Returns:
            List of split shift dictionaries
        """
        from models import SplitShift
        
        policy = Policy.get_policy_for_term(term_id)
        if not policy:
            raise ShiftValidationError(f"No policy found for term {term_id}")
        
        original_duration = DurationValidator.get_duration_minutes(start_time, end_time)
        max_duration = policy.max_shift_length
        min_break = policy.min_break_length
        
        # Calculate how many splits are needed
        split_count = (original_duration + max_duration - 1) // max_duration  # Ceiling division
        split_duration = original_duration // split_count
        
        # Ensure split duration doesn't go below minimum
        if split_duration < policy.min_shift_length:
            # Reduce split count to maintain minimum duration
            split_count = original_duration // policy.min_shift_length
            split_duration = original_duration // split_count
        
        # Generate split shifts
        split_shifts = []
        current_start = datetime.combine(shift_date, start_time)
        
        for i in range(split_count):
            current_end = current_start + timedelta(minutes=split_duration)
            
            # Adjust last shift to use remaining time
            if i == split_count - 1:
                original_end = datetime.combine(shift_date, end_time)
                if original_end < current_end:
                    current_end = original_end
                elif original_end > current_end:
                    # Use all remaining time for last shift
                    current_end = original_end
            
            split_shifts.append({
                'start_time': current_start.time(),
                'end_time': current_end.time(),
                'date': shift_date,
                'user_id': user_id,
                'duration_minutes': (current_end - current_start).total_seconds() / 60,
                'split_sequence': i + 1,
                'total_splits': split_count
            })
            
            # Add break time for next shift (except for last split)
            if i < split_count - 1:
                current_start = current_end + timedelta(minutes=min_break)
        
        # Log the split operation
        split_reason = (f"Automatic split: {original_duration} minutes exceeds "
                       f"maximum {max_duration} minutes")
        
        split_log = SplitShift(
            term_id=term_id,
            user_id=user_id,
            original_start_time=start_time,
            original_end_time=end_time,
            original_duration_minutes=original_duration,
            proposed_date=shift_date,
            split_count=split_count,
            break_minutes=min_break,
            split_reason=split_reason,
            schedule_generation_session=session_id or str(uuid.uuid4())
        )
        
        db.session.add(split_log)
        db.session.commit()
        
        return split_shifts
    
    @staticmethod
    def auto_split_long_shifts(term_id: int, proposed_shifts: List[Dict], 
                             session_id: str = None) -> Tuple[List[Dict], List[Dict]]:
        """
        Automatically split shifts exceeding maximum duration (Issue #28)
        
        Args:
            term_id: Term ID to get policy for
            proposed_shifts: List of shift dictionaries
            session_id: Generation session ID
            
        Returns:
            Tuple of (compliant_shifts, split_operations)
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
            
        policy = Policy.get_policy_for_term(term_id)
        if not policy:
            raise ShiftValidationError(f"No policy found for term {term_id}")
        
        compliant_shifts = []
        split_operations = []
        
        for shift_data in proposed_shifts:
            duration = DurationValidator.get_duration_minutes(
                shift_data['start_time'], 
                shift_data['end_time']
            )
            
            # Check if shift exceeds maximum duration
            if duration > policy.max_shift_length:
                # Split the shift
                split_shifts = AutomaticSplitSystem.split_and_log_shift(
                    term_id=term_id,
                    user_id=shift_data.get('user_id'),
                    start_time=shift_data['start_time'],
                    end_time=shift_data['end_time'],
                    shift_date=shift_data['date'],
                    session_id=session_id
                )
                
                # Add split shifts to compliant list
                compliant_shifts.extend(split_shifts)
                
                # Track the split operation
                split_operations.append({
                    'original_shift': shift_data,
                    'split_shifts': split_shifts,
                    'original_duration': duration,
                    'split_count': len(split_shifts)
                })
                
            else:
                # Shift is already compliant
                compliant_shifts.append(shift_data)
        
        return compliant_shifts, split_operations
    
    @staticmethod
    def get_split_stats(term_id: int, session_id: str = None) -> Dict:
        """
        Get statistics about split shifts for a term or session
        
        Args:
            term_id: Term ID
            session_id: Optional session ID to filter by
            
        Returns:
            Dictionary with split statistics
        """
        from models import SplitShift
        
        query = SplitShift.query.filter_by(term_id=term_id)
        
        if session_id:
            query = query.filter_by(schedule_generation_session=session_id)
            
        splits = query.all()
        
        if not splits:
            return {
                'total_splits': 0,
                'total_original_shifts': 0,
                'avg_original_duration': 0,
                'avg_split_count': 0,
                'total_time_saved': 0,
                'most_recent': None
            }
        
        original_durations = [s.original_duration_minutes for s in splits]
        split_counts = [s.split_count for s in splits]
        max_allowed = Policy.get_policy_for_term(term_id).max_shift_length
        
        # Calculate time saved (excess time that was eliminated)
        time_saved = sum(max(0, duration - max_allowed) for duration in original_durations)
        
        return {
            'total_splits': len(splits),
            'total_original_shifts': len(splits),
            'avg_original_duration': sum(original_durations) / len(original_durations),
            'avg_split_count': sum(split_counts) / len(split_counts),
            'longest_original': max(original_durations),
            'total_time_saved': time_saved,
            'most_recent': max(splits, key=lambda s: s.created_at).created_at,
            'session_id': session_id
        }

class DurationValidator:
    """
    Utility class for validating shift durations against policy constraints
    Used by schedule generators and manual shift editing (Issue #26)
"""    @staticmethod
    def validate_shift_duration(term_id: int, start_time: dt_time, end_time: dt_time) -> Tuple[bool, Optional[str]]:
        """
        Validate if a shift duration meets policy constraints
        
        Args:
            term_id: ID of the term to check policy against
            start_time: Start time of the shift
            end_time: End time of the shift
            
        Returns:
            Tuple of (is_valid, error_message)
            
        Raises:
            ShiftValidationError: If no policy found for term
        """
        policy = Policy.get_policy_for_term(term_id)
        if not policy:
            raise ShiftValidationError(f"No policy found for term {term_id}")
            
        return policy.validate_shift_times(start_time, end_time)
    
    @staticmethod
    def get_duration_minutes(start_time: dt_time, end_time: dt_time, shift_date=None) -> int:
        """
        Calculate shift duration in minutes, handling overnight shifts
        
        Args:
            start_time: Start time of shift
            end_time: End time of shift  
            shift_date: Date of shift (optional, defaults to today)
            
        Returns:
            Duration in minutes
        """
        if shift_date is None:
            shift_date = datetime.today().date()
            
        start_dt = datetime.combine(shift_date, start_time)
        end_dt = datetime.combine(shift_date, end_time)
        
        # Handle overnight shifts
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
            
        duration = (end_dt - start_dt).total_seconds() / 60
        return int(duration)
    
    @staticmethod
    def enforce_minimum_duration(term_id: int, duration_minutes: int) -> bool:
        """Check if duration meets minimum requirement"""
        policy = Policy.get_policy_for_term(term_id)
        if not policy:
            return False
        return duration_minutes >= policy.min_shift_length
    
    @staticmethod
    def enforce_maximum_duration(term_id: int, duration_minutes: int) -> bool:
        """Check if duration meets maximum requirement"""
        policy = Policy.get_policy_for_term(term_id)
        if not policy:
            return False
        return duration_minutes <= policy.max_shift_length
    
    @staticmethod
    def get_policy_constraints(term_id: int) -> Optional[dict]:
        """
        Get policy constraints for a term
        
        Returns:
            Dictionary with min_duration, max_duration, or None if no policy
        """
        policy = Policy.get_policy_for_term(term_id)
        if not policy:
            return None
            
        return {
            'min_duration': policy.min_shift_length,
            'max_duration': policy.max_shift_length,
            'min_break': policy.min_break_length,
            'max_break': policy.max_break_length
        }
    
    @staticmethod
    def validate_shift_before_save(shift_data: dict) -> Tuple[bool, Optional[str]]:
        """
        Validate a shift before saving to database
        Used by forms and schedule generators
        
        Args:
            shift_data: Dictionary with term_id, start_time, end_time
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            return DurationValidator.validate_shift_duration(
                shift_data['term_id'],
                shift_data['start_time'], 
                shift_data['end_time']
            )
        except ShiftValidationError as e:
            return False, str(e)
    
    @staticmethod
    def generate_error_message(term_id: int, duration_minutes: int) -> str:
        """Generate user-friendly error message for constraint violations"""
        policy = Policy.get_policy_for_term(term_id)
        if not policy:
            return f"No policy configured for term {term_id}"
            
        if duration_minutes < policy.min_shift_length:
            return (f"Shift too short: {duration_minutes} minutes. "
                   f"Minimum required: {policy.min_shift_length} minutes "
                   f"({policy.min_shift_length//60}h {policy.min_shift_length%60}m)")
        
        if duration_minutes > policy.max_shift_length:
            return (f"Shift too long: {duration_minutes} minutes. "
                   f"Maximum allowed: {policy.max_shift_length} minutes "
                   f"({policy.max_shift_length//60}h {policy.max_shift_length%60}m)")
        
        return f"Duration {duration_minutes} minutes is valid"

class ScheduleGenerator:
    """
    Enhanced schedule generation with automatic rejection system (Issues #26 & #27)
    Prevents impractical shifts from being created and provides coverage warnings
    """
    
    @staticmethod
    def validate_proposed_shift(term_id: int, user_id: int, start_time: dt_time, 
                              end_time: dt_time, shift_date=None) -> Tuple[bool, Optional[str]]:
        """
        Validate a proposed shift before adding to schedule
        
        Args:
            term_id: Term ID
            user_id: User ID
            start_time: Proposed start time
            end_time: Proposed end time
            shift_date: Date of shift
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate duration constraints
        is_valid, error = DurationValidator.validate_shift_duration(
            term_id, start_time, end_time
        )
        
        if not is_valid:
            return False, f"Duration constraint violation: {error}"
        
        # TODO: Add additional validations:
        # - Check for scheduling conflicts
        # - Validate break time requirements 
        # - Check availability
        
        return True, None
    
    @staticmethod
    def generate_schedule_with_auto_processing(term_id: int, proposed_shifts: List[Dict], 
                                             session_id: str = None) -> Dict:
        """
        Generate schedule with automatic rejection and splitting (Issues #27 & #28)
        
        Args:
            term_id: Term ID
            proposed_shifts: List of proposed shift data
            session_id: Optional session ID for tracking
            
        Returns:
            Dictionary with generation results, rejections, splits, and warnings
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        # Step 1: Automatic splitting of long shifts (Issue #28)
        after_split_shifts, split_operations = (
            AutomaticSplitSystem.auto_split_long_shifts(
                term_id, proposed_shifts, session_id
            )
        )
        
        # Step 2: Automatic rejection of short shifts (Issue #27) 
        valid_shifts, rejected_shifts, coverage_warning = (
            AutomaticRejectionSystem.auto_reject_short_shifts(
                term_id, after_split_shifts, session_id
            )
        )
        
        # Step 3: Additional validation for remaining shifts
        final_valid_shifts = []
        additional_rejections = []
        
        for shift_data in valid_shifts:
            is_valid, error = ScheduleGenerator.validate_proposed_shift(
                term_id=term_id,
                user_id=shift_data.get('user_id'),
                start_time=shift_data['start_time'],
                end_time=shift_data['end_time'],
                shift_date=shift_data['date']
            )
            
            if is_valid:
                final_valid_shifts.append(shift_data)
            else:
                # Log additional rejections
                AutomaticRejectionSystem.reject_and_log_shift(
                    term_id=term_id,
                    user_id=shift_data.get('user_id'),
                    start_time=shift_data['start_time'],
                    end_time=shift_data['end_time'],
                    shift_date=shift_data['date'],
                    reason=error,
                    rejection_type='policy',
                    session_id=session_id
                )
                additional_rejections.append({**shift_data, 'rejection_reason': error})
        
        # Get statistics
        rejection_stats = AutomaticRejectionSystem.get_rejection_stats(term_id, session_id)
        split_stats = AutomaticSplitSystem.get_split_stats(term_id, session_id)
        
        return {
            'session_id': session_id,
            'original_proposed': proposed_shifts,
            'after_splits': after_split_shifts,
            'final_valid_shifts': final_valid_shifts,
            'rejected_shifts': rejected_shifts + additional_rejections,
            'split_operations': split_operations,
            'coverage_warning': coverage_warning,
            'rejection_stats': rejection_stats,
            'split_stats': split_stats,
            'processing_summary': {
                'original_count': len(proposed_shifts),
                'after_split_count': len(after_split_shifts),
                'final_accepted_count': len(final_valid_shifts),
                'total_rejected': len(rejected_shifts) + len(additional_rejections),
                'total_split_operations': len(split_operations),
                'splits_created': sum(op['split_count'] for op in split_operations)
            }
        }
    
    @staticmethod
    def check_coverage_gaps(rejected_shifts: List[Dict], required_coverage: List[Dict]) -> List[Dict]:
        """
        Check if rejected shifts cause coverage gaps and warn supervisor (Issue #27)
        
        Args:
            rejected_shifts: List of rejected shift data
            required_coverage: List of required coverage periods
            
        Returns:
            List of coverage gaps that may need manual intervention
        """
        coverage_gaps = []
        
        for coverage_period in required_coverage:
            # Check if any rejected shifts would have covered this period
            covering_rejections = []
            for rejection in rejected_shifts:
                # Simple overlap check (can be enhanced)
                if (rejection['start_time'] <= coverage_period['end_time'] and 
                    rejection['end_time'] >= coverage_period['start_time']):
                    covering_rejections.append(rejection)
            
            if covering_rejections:
                coverage_gaps.append({
                    'period': coverage_period,
                    'rejected_shifts': covering_rejections,
                    'gap_severity': 'high' if len(covering_rejections) > 1 else 'medium'
                })
        
        return coverage_gaps
    
    @staticmethod
    def generate_valid_shift_options(term_id: int, base_start_time: dt_time) -> list:
        """
        Generate list of valid shift durations from a start time
        
        Args:
            term_id: Term to get constraints for
            base_start_time: Proposed start time
            
        Returns:
            List of valid end times that meet duration constraints
        """
        constraints = DurationValidator.get_policy_constraints(term_id)
        if not constraints:
            return []
        
        valid_options = []
        
        # Generate options from minimum to maximum duration in 15-minute increments
        min_duration = constraints['min_duration']
        max_duration = constraints['max_duration']
        
        for duration in range(min_duration, max_duration + 1, 15):
            start_dt = datetime.combine(datetime.today(), base_start_time)
            end_dt = start_dt + timedelta(minutes=duration)
            valid_options.append(end_dt.time())
        
        return valid_options