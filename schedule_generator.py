"""
Schedule Generator for Issue #32: Gap Prevention
Intelligent shift generation that avoids fragmented 15-30 minute slots
"""

from datetime import datetime, timedelta, time, date
from models import db, Shift, Policy, ShiftGap, User, Availability, StaffingNeeds
from typing import List, Dict, Tuple, Optional


class ScheduleGenerator:
    """
    Intelligent schedule generator that prevents fragmented gaps (Issue #32)
    """
    
    def __init__(self, term_id: int):
        self.term_id = term_id
        self.policy = Policy.get_policy_with_defaults(term_id)
        self.generated_shifts = []
        self.rejected_shifts = []
        self.warnings = []
    
    def generate_schedule(self, start_date: date, end_date: date, dry_run: bool = False) -> Dict:
        """
        Generate a complete schedule avoiding fragmented gaps
        
        Args:
            start_date: Start date for schedule generation
            end_date: End date for schedule generation
            dry_run: If True, don't save to database
            
        Returns:
            Dictionary with generation results and statistics
        """
        self.generated_shifts = []
        self.rejected_shifts = []
        self.warnings = []
        
        current_date = start_date
        
        while current_date <= end_date:
            # Generate shifts for this date
            daily_shifts = self._generate_daily_schedule(current_date)
            self.generated_shifts.extend(daily_shifts)
            current_date += timedelta(days=1)
        
        # Post-process to detect and resolve gaps
        self._post_process_gaps()
        
        # Save to database if not dry run
        if not dry_run:
            self._save_generated_schedule()
        
        return self._get_generation_summary()
    
    def _generate_daily_schedule(self, target_date: date) -> List[Shift]:
        """Generate shifts for a specific date"""
        daily_shifts = []
        
        # Get staffing needs for this day
        day_of_week = target_date.weekday()  # 0 = Monday
        staffing_needs = StaffingNeeds.query.filter_by(
            term_id=self.term_id,
            day_of_week=day_of_week
        ).order_by(StaffingNeeds.start_time).all()
        
        # Get available users for this day
        available_users = self._get_available_users(target_date, day_of_week)
        
        for need in staffing_needs:
            # Generate shifts to meet this staffing need
            shifts = self._generate_shifts_for_need(need, target_date, available_users)
            daily_shifts.extend(shifts)
        
        # Sort shifts by user and time for gap detection
        daily_shifts.sort(key=lambda s: (s.user_id, s.start_time))
        
        return daily_shifts
    
    def _generate_shifts_for_need(self, need: StaffingNeeds, target_date: date, available_users: List[User]) -> List[Shift]:
        """Generate shifts to meet a specific staffing need"""
        shifts = []
        
        # Calculate total duration needed
        start_dt = datetime.combine(target_date, need.start_time)
        end_dt = datetime.combine(target_date, need.end_time)
        
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        
        total_duration = (end_dt - start_dt).total_seconds() / 60
        
        # Determine optimal shift length to avoid gaps
        optimal_duration = self._calculate_optimal_shift_duration(total_duration)
        
        # Assign users to cover the time period
        current_time = need.start_time
        users_assigned = 0
        
        for user in available_users:
            if users_assigned >= need.required_count:
                break
            
            # Check if user is available for this time slot
            if self._is_user_available(user, target_date, current_time, optimal_duration):
                # Check for potential gaps with existing shifts
                proposed_shift = self._create_proposed_shift(user, target_date, current_time, optimal_duration)
                
                if self._validate_shift_for_gaps(proposed_shift, user):
                    shifts.append(proposed_shift)
                    users_assigned += 1
        
        return shifts
    
    def _calculate_optimal_shift_duration(self, total_duration: float) -> int:
        """
        Calculate optimal shift duration to minimize gaps (Issue #32)
        
        Args:
            total_duration: Total time period to cover in minutes
            
        Returns:
            Optimal shift duration in minutes
        """
        min_duration = self.policy.min_shift_length
        max_duration = self.policy.max_shift_length
        
        # If prefer longer shifts is enabled, start with max duration
        if self.policy.prefer_longer_shifts:
            # Try to use the maximum duration that fits well
            if total_duration <= max_duration:
                return int(total_duration)
            
            # Find a duration that divides evenly or leaves acceptable gaps
            for duration in range(max_duration, min_duration - 1, -15):  # Try in 15-minute decrements
                remainder = total_duration % duration
                
                # If remainder is zero (perfect fit) or large enough to not be problematic
                if remainder == 0 or remainder > self.policy.max_gap_threshold:
                    return duration
        
        # Default to a safe middle ground
        return min(max_duration, max(min_duration, int(total_duration / 2)))
    
    def _is_user_available(self, user: User, target_date: date, start_time: time, duration_minutes: int) -> bool:
        """Check if user is available for the proposed shift time"""
        # Get user's availability for this day
        day_name = target_date.strftime('%a')  # Mon, Tue, etc.
        
        availabilities = Availability.query.filter_by(
            user_id=user.user_id,
            term_id=self.term_id,
            day_of_week=day_name
        ).all()
        
        if not availabilities:
            return False
        
        # Calculate end time for proposed shift
        start_dt = datetime.combine(target_date, start_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        end_time = end_dt.time()
        
        # Check if any availability window covers this time
        for avail in availabilities:
            if (avail.start_time <= start_time <= avail.end_time and
                avail.start_time <= end_time <= avail.end_time):
                return True
        
        return False
    
    def _create_proposed_shift(self, user: User, target_date: date, start_time: time, duration_minutes: int) -> Shift:
        """Create a proposed shift object (not yet saved to database)"""
        start_dt = datetime.combine(target_date, start_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        end_time = end_dt.time()
        
        return Shift(
            term_id=self.term_id,
            user_id=user.user_id,
            date=target_date,
            start_time=start_time,
            end_time=end_time,
            was_manually_adjusted=False
        )
    
    def _validate_shift_for_gaps(self, proposed_shift: Shift, user: User) -> bool:
        """
        Validate that proposed shift won't create problematic gaps or transition time violations (Issue #32 & #35)
        
        Args:
            proposed_shift: The shift being considered
            user: User the shift is assigned to
            
        Returns:
            True if shift is acceptable, False if it would create problematic gaps or transition violations
        """
        # Get existing shifts for this user on this date
        existing_shifts = [s for s in self.generated_shifts 
                          if s.user_id == user.user_id and s.date == proposed_shift.date]
        
        if not existing_shifts:
            return True  # No existing shifts, no gap concerns
        
        # Check for gaps and transition time violations with each existing shift
        for existing_shift in existing_shifts:
            gap_duration = self._calculate_gap_duration(existing_shift, proposed_shift)
            
            if gap_duration is not None:  # There is a gap
                # Issue #32: Check for problematic gaps
                if self.policy.min_gap_threshold <= gap_duration <= self.policy.max_gap_threshold:
                    # This would create a problematic gap
                    self.warnings.append(f"Rejected shift for {user.name} - would create {gap_duration}min gap")
                    return False
                
                # Issue #35: Check for transition time violations
                if gap_duration < self.policy.min_transition_time:
                    # This would violate minimum transition time
                    self.warnings.append(f"Rejected shift for {user.name} - insufficient transition time ({gap_duration}min < {self.policy.min_transition_time}min required)")
                    return False
        
        return True
    
    def _calculate_gap_duration(self, shift1: Shift, shift2: Shift) -> Optional[int]:
        """
        Calculate gap duration between two shifts, return None if no gap
        
        Args:
            shift1: First shift
            shift2: Second shift
            
        Returns:
            Gap duration in minutes, or None if shifts don't have a gap
        """
        # Determine which shift comes first
        if shift1.start_time <= shift2.start_time:
            first_shift, second_shift = shift1, shift2
        else:
            first_shift, second_shift = shift2, shift1
        
        # Calculate gap
        first_end = datetime.combine(first_shift.date, first_shift.end_time)
        second_start = datetime.combine(second_shift.date, second_shift.start_time)
        
        # Handle day boundary crossings
        if second_start < first_end:
            second_start += timedelta(days=1)
        
        # Check if there's actually a gap (not overlapping)
        if second_start <= first_end:
            return None  # No gap, shifts overlap or are adjacent
        
        gap_duration = (second_start - first_end).total_seconds() / 60
        return int(gap_duration) if gap_duration > 0 else None
    
    def _get_available_users(self, target_date: date, day_of_week: int) -> List[User]:
        """Get users available for the given date"""
        day_name = target_date.strftime('%a')
        
        # Get users with availability for this day
        available_users = db.session.query(User).join(Availability).filter(
            Availability.term_id == self.term_id,
            Availability.day_of_week == day_name
        ).distinct().all()
        
        return available_users
    
    def _post_process_gaps(self):
        """Post-process generated schedule to detect and resolve gaps"""
        # Group shifts by user and date
        user_date_shifts = {}
        
        for shift in self.generated_shifts:
            key = (shift.user_id, shift.date)
            if key not in user_date_shifts:
                user_date_shifts[key] = []
            user_date_shifts[key].append(shift)
        
        # Check for gaps and attempt auto-merge
        for (user_id, shift_date), shifts in user_date_shifts.items():
            if len(shifts) >= 2:
                self._attempt_gap_resolution(shifts, user_id)
    
    def _attempt_gap_resolution(self, shifts: List[Shift], user_id: int):
        """Attempt to resolve gaps between shifts for a user"""
        # Sort shifts by start time
        shifts.sort(key=lambda s: s.start_time)
        
        i = 0
        while i < len(shifts) - 1:
            current_shift = shifts[i]
            next_shift = shifts[i + 1]
            
            gap_duration = self._calculate_gap_duration(current_shift, next_shift)
            
            if (gap_duration is not None and 
                gap_duration <= self.policy.max_gap_threshold and
                self.policy.allow_gap_merging):
                
                # Try to merge shifts
                merged_shift = self._try_merge_shifts(current_shift, next_shift)
                
                if merged_shift:
                    # Replace the two shifts with the merged one
                    shifts[i] = merged_shift
                    shifts.pop(i + 1)
                    
                    # Update generated_shifts list
                    self.generated_shifts = [s for s in self.generated_shifts 
                                           if s != current_shift and s != next_shift]
                    self.generated_shifts.append(merged_shift)
                    
                    self.warnings.append(f"Auto-merged shifts for user {user_id} to eliminate {gap_duration}min gap")
                else:
                    # Merging failed, record warning
                    self.warnings.append(f"Unavoidable {gap_duration}min gap for user {user_id}")
                    i += 1
            else:
                i += 1
    
    def _try_merge_shifts(self, shift1: Shift, shift2: Shift) -> Optional[Shift]:
        """
        Try to merge two shifts into one
        
        Args:
            shift1: First shift
            shift2: Second shift
            
        Returns:
            Merged shift if possible, None otherwise
        """
        # Determine order
        if shift1.start_time <= shift2.start_time:
            first_shift, second_shift = shift1, shift2
        else:
            first_shift, second_shift = shift2, shift1
        
        # Create merged shift
        merged_start = first_shift.start_time
        merged_end = second_shift.end_time
        
        # Validate merged shift duration
        is_valid, error = self.policy.validate_shift_times(merged_start, merged_end)
        
        if is_valid:
            return Shift(
                term_id=self.term_id,
                user_id=first_shift.user_id,
                date=first_shift.date,
                start_time=merged_start,
                end_time=merged_end,
                was_manually_adjusted=True  # Mark as adjusted since it was merged
            )
        
        return None
    
    def _save_generated_schedule(self):
        """Save generated schedule to database"""
        try:
            for shift in self.generated_shifts:
                db.session.add(shift)
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            raise Exception(f"Failed to save generated schedule: {str(e)}")
    
    def _get_generation_summary(self) -> Dict:
        """Get summary of schedule generation process"""
        return {
            'total_shifts_generated': len(self.generated_shifts),
            'shifts_rejected': len(self.rejected_shifts),
            'warnings': self.warnings,
            'gap_prevention_active': True,
            'auto_merge_enabled': self.policy.allow_gap_merging,
            'gap_thresholds': {
                'min_gap_threshold': self.policy.min_gap_threshold,
                'max_gap_threshold': self.policy.max_gap_threshold
            },
            'policy_settings': {
                'min_shift_length': self.policy.min_shift_length,
                'max_shift_length': self.policy.max_shift_length,
                'prefer_longer_shifts': self.policy.prefer_longer_shifts
            }
        }


class GapAnalyzer:
    """
    Utility class for analyzing and managing gaps in existing schedules (Issue #32)
    """
    
    @staticmethod
    def analyze_term_gaps(term_id: int) -> Dict:
        """Analyze all gaps in a term's schedule"""
        # Detect all gaps
        gaps = ShiftGap.detect_all_gaps_for_term(term_id)
        
        # Get summary statistics
        summary = ShiftGap.get_gap_summary(term_id=term_id)
        
        # Get merge recommendations
        merge_recommendations = []
        for gap in gaps:
            if not gap.is_resolved:
                suggestion = gap.get_merge_suggestion()
                if suggestion and suggestion['can_merge']:
                    merge_recommendations.append({
                        'gap_id': gap.gap_id,
                        'user_name': gap.user.name,
                        'date': gap.date.strftime('%Y-%m-%d'),
                        'gap_duration': gap.gap_duration_minutes,
                        'suggestion': suggestion
                    })
        
        return {
            'total_gaps_detected': len(gaps),
            'gap_summary': summary,
            'merge_recommendations': merge_recommendations,
            'gaps_by_user': GapAnalyzer._group_gaps_by_user(gaps),
            'gaps_by_date': GapAnalyzer._group_gaps_by_date(gaps)
        }
    
    @staticmethod
    def _group_gaps_by_user(gaps: List[ShiftGap]) -> Dict:
        """Group gaps by user for analysis"""
        user_gaps = {}
        for gap in gaps:
            if gap.user_id not in user_gaps:
                user_gaps[gap.user_id] = {
                    'user_name': gap.user.name,
                    'gaps': [],
                    'total_gap_time': 0,
                    'avg_gap_duration': 0
                }
            
            user_gaps[gap.user_id]['gaps'].append(gap)
            user_gaps[gap.user_id]['total_gap_time'] += gap.gap_duration_minutes
        
        # Calculate averages
        for user_id, data in user_gaps.items():
            if data['gaps']:
                data['avg_gap_duration'] = data['total_gap_time'] / len(data['gaps'])
        
        return user_gaps
    
    @staticmethod
    def _group_gaps_by_date(gaps: List[ShiftGap]) -> Dict:
        """Group gaps by date for analysis"""
        date_gaps = {}
        for gap in gaps:
            date_str = gap.date.strftime('%Y-%m-%d')
            if date_str not in date_gaps:
                date_gaps[date_str] = []
            date_gaps[date_str].append(gap)
        
        return date_gaps
    
    @staticmethod
    def batch_merge_gaps(gap_ids: List[int], user_id: int) -> Dict:
        """Attempt to merge multiple gaps in batch"""
        results = {
            'successful_merges': 0,
            'failed_merges': 0,
            'errors': []
        }
        
        for gap_id in gap_ids:
            gap = ShiftGap.query.get(gap_id)
            if gap and not gap.is_resolved:
                try:
                    if gap.attempt_auto_merge(user_id):
                        results['successful_merges'] += 1
                    else:
                        results['failed_merges'] += 1
                        results['errors'].append(f"Gap {gap_id}: {gap.merge_blocked_reason}")
                except Exception as e:
                    results['failed_merges'] += 1
                    results['errors'].append(f"Gap {gap_id}: {str(e)}")
        
        return results