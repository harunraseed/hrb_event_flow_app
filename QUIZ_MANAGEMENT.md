# Quiz Management Features 🧠

## Overview
The quiz system now includes comprehensive management options for administrators to control quiz lifecycle and data.

## New Features

### 🗑️ Delete Quiz
**Purpose**: Permanently remove the entire quiz and all associated data.

**What gets deleted**:
- ✅ All quiz questions
- ✅ All participant attempts  
- ✅ All quiz answers
- ✅ Quiz configuration
- ✅ Quiz statistics

**How to use**:
1. Go to Event Dashboard → Quiz
2. Click "Delete Quiz" button
3. Confirm by typing "DELETE QUIZ" 
4. Quiz is permanently removed

**Safety**: 
- ⚠️ Requires double confirmation
- ⚠️ Action cannot be undone
- ⚠️ Shows impact summary before deletion

### 🔄 Reset Quiz  
**Purpose**: Clear participant data while keeping questions and configuration.

**What gets reset**:
- ✅ All participant attempts
- ✅ All quiz answers  
- ✅ Quiz state (stopped, inactive)
- ✅ Start/end times

**What gets preserved**:
- ✅ Quiz questions
- ✅ Quiz configuration
- ✅ Participant limit settings
- ✅ Timer settings

**How to use**:
1. Go to Event Dashboard → Quiz
2. Click "Reset Quiz" button (only shows if attempts exist)
3. Confirm the action
4. Quiz is reset and ready for new participants

**Use cases**:
- 🎯 Run the same quiz again with fresh data
- 🎯 Test quiz before real event
- 🎯 Remove test participants before going live

## Button Visibility

| Quiz State | Delete Quiz | Reset Quiz |
|------------|-------------|------------|
| **No questions** | ✅ Visible | ❌ Hidden |
| **Has questions, no attempts** | ✅ Visible | ❌ Hidden |
| **Has attempts** | ✅ Visible | ✅ Visible |

## Safety Features

### Delete Quiz Safety:
```
⚠️ WARNING: This will permanently delete the entire quiz "Quiz Name" and ALL related data including:

• X participant attempts
• All quiz questions  
• All quiz answers
• Quiz configuration

This action CANNOT be undone!

Type "DELETE QUIZ" to confirm:
```

### Reset Quiz Safety:
```
⚠️ This will reset the quiz and remove all participant data:

• X participant attempts will be deleted
• All quiz answers will be removed
• Quiz will be stopped and reset to inactive
• Questions and configuration will be kept

Participants will need to rejoin the quiz.
```

## API Endpoints

### Delete Quiz
```http
POST /event/<event_id>/quiz/delete
```

**Response**:
```json
{
  "success": true,
  "message": "Quiz 'Quiz Name' deleted successfully!"
}
```

### Reset Quiz  
```http
POST /event/<event_id>/quiz/reset
```

**Response**:
```json
{
  "success": true,
  "message": "Quiz reset successfully! Removed 15 participant attempts.",
  "attempts_removed": 15
}
```

## Best Practices

### When to Delete Quiz:
- ❌ Quiz was created incorrectly
- ❌ Starting completely over  
- ❌ Quiz no longer needed
- ❌ Event cancelled

### When to Reset Quiz:
- 🔄 Testing phase complete, ready for real event
- 🔄 Want to run same quiz again
- 🔄 Clear test data before going live
- 🔄 Start fresh with same questions

### Workflow Recommendations:

1. **Development Phase**:
   ```
   Create Quiz → Add Questions → Test → Reset → Go Live
   ```

2. **Production Phase**:
   ```
   Configure → Start → Monitor → End → Reset (if rerunning)
   ```

3. **Cleanup Phase**:
   ```
   Export Results → Delete Quiz (if no longer needed)
   ```

## Error Handling

Both features include comprehensive error handling:
- Database rollback on failures
- User-friendly error messages  
- Network error handling
- Validation checks

## Mobile Support

Both delete and reset functions work seamlessly on mobile devices with:
- Touch-friendly confirmation dialogs
- Responsive button layouts
- Clear visual feedback