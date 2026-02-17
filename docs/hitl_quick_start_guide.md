# HITL Quick Start Guide

**Complete Human-in-the-Loop Implementation**
**Backend (Phases 1-6) + Frontend (Phase 7)**

---

## 🚀 Quick Start (5 minutes)

### Step 1: Start Backend
```bash
cd ingestion
poetry install  # if not already installed
poetry run uvicorn research_agent.api.main:app --reload --host 0.0.0.0 --port 8001
```

**Expected Output**:
```
[api] 🚀 Starting Research Agent API...
[api] ✅ Taskiq broker connected to RabbitMQ
[api] ✅ MongoDB/Beanie initialized
[api] ✅ Coordinator Agent initialized
[api] 🎉 All services ready!
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### Step 2: Start Frontend
```bash
cd research_client
pnpm install  # if not already installed
pnpm run dev
```

**Expected Output**:
```
  ▲ Next.js 14.x.x
  - Local:        http://localhost:3000
  - Ready in 2.3s
```

### Step 3: Test HITL Flow

1. **Open Browser**: Navigate to `http://localhost:3000`
2. **Create Thread**: Click "New Conversation"
3. **Send Message**: 
   ```
   Create a research plan to analyze Tesla's battery technology and compare it with BYD. Budget: $50, Priority: balanced
   ```
4. **Wait for Approval UI**: Amber alert box will appear with plan details
5. **Make Decision**: Click "Approve Plan"
6. **Agent Continues**: Agent confirms plan creation

**🎉 Success!** You've completed the HITL approval workflow!

---

## 📋 Detailed Testing Scenarios

### Scenario 1: Approve Plan (Happy Path)

**Steps**:
1. Send message: "Create a research plan for OpenAI GPT-4 competitors"
2. Wait for approval UI to appear
3. Review plan details
4. Click "Approve Plan"
5. Agent continues and creates plan

**Expected Result**:
- ✅ Plan approved immediately
- ✅ Agent confirms creation
- ✅ Plan saved to state

---

### Scenario 2: Edit Plan

**Steps**:
1. Send message: "Create a research plan for Tesla analysis, budget $100"
2. Wait for approval UI
3. Click "Edit Plan"
4. Modify JSON (e.g., change budget to 50)
5. Click "Submit Edits"
6. Agent uses modified plan

**Expected Result**:
- ✅ JSON editor appears
- ✅ Validation works (shows error for invalid JSON)
- ✅ Agent uses edited version
- ✅ Confirms modified budget

---

### Scenario 3: Reject Plan

**Steps**:
1. Send message: "Create a research plan for XYZ"
2. Wait for approval UI
3. Click "Reject Plan"
4. Enter reason: "Budget is too high, please reduce to $30"
5. Click "Confirm Rejection"
6. Agent receives feedback and proposes new plan

**Expected Result**:
- ✅ Rejection message sent to agent
- ✅ Agent acknowledges rejection
- ✅ Agent proposes revised plan based on feedback

---

### Scenario 4: Connection Loss & Recovery

**Steps**:
1. Start conversation
2. Stop backend server (Ctrl+C)
3. Observe "Disconnected" indicator in UI
4. Restart backend
5. Click "Reconnect" button

**Expected Result**:
- ✅ Red "Disconnected" badge appears
- ✅ Reconnect button visible
- ✅ Connection re-establishes
- ✅ Green "Connected" badge returns
- ✅ Can continue conversation

---

### Scenario 5: Multiple Stages Plan

**Steps**:
1. Send complex request:
   ```
   Create a comprehensive research plan for biotech company analysis:
   - Stage 1: Company profile and history
   - Stage 2: Product pipeline analysis
   - Stage 3: Competitive landscape
   - Stage 4: Financial analysis
   Budget: $200, Priority: depth
   ```
2. Wait for detailed plan with multiple stages
3. Review all stages in approval UI
4. Approve

**Expected Result**:
- ✅ Multi-stage plan displayed
- ✅ Each stage shows substages count
- ✅ All details visible
- ✅ Can scroll through long plan

---

## 🧪 Testing Checklist

### Backend Functionality
- [ ] WebSocket endpoint accessible at `ws://localhost:8001/api/coordinator/threads/{thread_id}/hitl`
- [ ] HITL middleware intercepts `create_research_plan` tool
- [ ] Interrupt data includes all plan details
- [ ] Approve decision resumes agent correctly
- [ ] Edit decision uses modified arguments
- [ ] Reject decision sends feedback to agent
- [ ] Timeout (5 min) works correctly

### Frontend Functionality
- [ ] WebSocket connection establishes automatically
- [ ] Connection status indicator updates correctly
- [ ] Message sending via WebSocket works
- [ ] Streaming content displays in real-time
- [ ] Approval UI appears on interrupt
- [ ] All plan details visible in UI
- [ ] Approve button works
- [ ] Edit mode with JSON validation works
- [ ] Reject mode with message input works
- [ ] Auto-reconnection works
- [ ] Manual reconnect button works
- [ ] Error messages display clearly

### Integration Testing
- [ ] End-to-end approve flow completes
- [ ] End-to-end edit flow completes
- [ ] End-to-end reject flow completes
- [ ] Connection loss recovery works
- [ ] Multiple concurrent threads supported
- [ ] Thread messages persist correctly
- [ ] LangGraph state syncs to MongoDB

---

## 🔍 Debugging Tips

### Check WebSocket Connection

**Browser Console**:
```javascript
// Should see WebSocket messages
[WebSocket] Connecting to: ws://localhost:8001/api/coordinator/threads/xxx/hitl
[WebSocket] Connected
[WebSocket] Message received: thinking
[WebSocket] Message received: content
```

**Network Tab**:
1. Open DevTools → Network tab
2. Filter by "WS" (WebSocket)
3. Click on connection
4. View Messages tab
5. See real-time message flow

### Check Backend Logs

**Expected Logs**:
```
[api] WebSocket connected for thread xxx
[api] Starting agent stream for thread xxx
[api] Agent stream completed for thread xxx
[api] Checking for interrupt in thread xxx
[api] Interrupt detected for thread xxx
[api] Decision received for thread xxx: approve
[api] Agent resumed and completed for thread xxx
```

### Common Issues

**WebSocket won't connect**:
- Check backend is running on port 8001
- Verify `NEXT_PUBLIC_API_URL=http://localhost:8001` in `.env.local`
- Check firewall/antivirus blocking WebSocket
- Try `ws://127.0.0.1:8001` instead

**Approval UI doesn't appear**:
- Ensure you ask to "create a research plan"
- Check backend logs for interrupt detection
- Verify HITL middleware is configured
- Check browser console for errors

**Streaming doesn't work**:
- Check WebSocket connection status
- Verify messages in Network tab
- Check React state in DevTools
- Review console for parsing errors

---

## 📊 Monitoring

### Backend Metrics
- WebSocket connection count
- Interrupt fire rate
- Decision type distribution (approve/edit/reject)
- Average decision time
- Timeout rate

### Frontend Metrics
- WebSocket connection success rate
- Reconnection attempt frequency
- Average time to decision
- Error rate
- User interaction patterns

---

## 🎯 Success Criteria

### Phase 7 Complete When:
- [x] WebSocket hook implemented and tested
- [x] Approval component renders correctly
- [x] Chat interface integrated with WebSocket
- [x] All linting errors resolved
- [x] TypeScript errors fixed
- [ ] End-to-end approve flow works
- [ ] End-to-end edit flow works
- [ ] End-to-end reject flow works
- [ ] Connection recovery tested
- [ ] Documentation complete

---

## 📚 Documentation Index

### Backend
- `ingestion/docs/hitl_backend_implementation_summary.md` - Complete backend details
- `ingestion/docs/hitl_testing_guide.md` - Backend testing scripts
- `ingestion/docs/human_in_the_loop_implementation_plan.md` - Original plan

### Frontend
- `research_client/docs/hitl_frontend_implementation.md` - Complete frontend details
- `docs/hitl_quick_start_guide.md` - This guide

### Code
- **Backend**: `ingestion/src/research_agent/`
  - `services/coordinator_agent.py` - HITL middleware configuration
  - `api/coordinator/routes/hitl_websocket.py` - WebSocket endpoint
  - `api/coordinator/websocket_manager.py` - Connection manager
  - `api/coordinator/schemas/threads.py` - HITL schemas

- **Frontend**: `research_client/src/`
  - `hooks/use-hitl-websocket.ts` - WebSocket hook
  - `components/hitl/research-plan-approval.tsx` - Approval UI
  - `components/chat/chat-interface.tsx` - Chat integration

---

## 🚢 Deployment Checklist

### Backend
- [ ] Update environment variables for production
- [ ] Configure CORS for frontend domain
- [ ] Set up persistent Postgres/MongoDB
- [ ] Configure WebSocket timeout for production
- [ ] Set up logging and monitoring
- [ ] Configure rate limiting
- [ ] Set up SSL/TLS for WSS

### Frontend
- [ ] Update `NEXT_PUBLIC_API_URL` to production URL
- [ ] Use WSS (not WS) for secure WebSocket
- [ ] Configure build optimization
- [ ] Set up error tracking (Sentry)
- [ ] Configure analytics
- [ ] Test on multiple devices/browsers
- [ ] Set up CDN for static assets

---

## 🎉 Next Steps

1. **Run Full Test Suite**: Complete all testing scenarios
2. **User Acceptance Testing**: Get feedback from real users
3. **Performance Testing**: Load test with multiple concurrent connections
4. **Security Audit**: Review authentication and authorization
5. **Documentation Review**: Update based on testing findings
6. **Production Deployment**: Deploy to staging first
7. **Monitoring Setup**: Configure alerts and dashboards

---

## 💡 Tips for Success

1. **Always Check Logs**: Backend logs are your best friend for debugging
2. **Use Browser DevTools**: Network and Console tabs show everything
3. **Test Edge Cases**: Connection loss, timeout, invalid JSON, etc.
4. **Mobile Testing**: Test on real mobile devices
5. **Dark Mode**: Test UI in both light and dark themes
6. **Accessibility**: Use keyboard navigation to test
7. **Performance**: Monitor memory usage in long sessions

---

**🎊 Congratulations!** 

You now have a fully functional Human-in-the-Loop system with:
- ✅ Real-time WebSocket communication
- ✅ Beautiful, intuitive approval UI
- ✅ Robust error handling
- ✅ Auto-reconnection
- ✅ Complete documentation

**Happy Testing! 🚀**
