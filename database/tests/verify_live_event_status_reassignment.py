"""Opt-in real SCRUM-48 reassignment verification on a retained labelled fixture.

Uses only existing visible development accounts and normal Auth/API calls.
Canonical event/history must stay unchanged; one assignment append is intended.
No pytest discovery or automatic execution. Credentials/tokens stay in memory.
"""
import argparse
from uuid import UUID

from verify_live_event_status_history import Harness, require


# AC5-X3 (cross-cutting): stale assignment revokes reads/actions without rewriting historical actors.
def verify_reassignment(h, event):
    h.report.update({'case':'AC5-X3','event_id':event,'write_scope':'One intended assignment append; no status reset or deletion'})
    for role,email in [('owner','event_organiser@example.com'),('assigned','event_coordinator2@example.com'),('replacement','event_coordinator1@example.com'),('manager','event_operations_manager@example.com')]:h.login(role,email)
    before=h.snapshot(event)
    require(before['event']['event_name'].startswith('SCRUM-48 real API overlap check - '),'Not labelled fixture')
    require(before['event']['organiser_id']==h.identities['owner']['id'],'Fixture owner differs from verified organiser')
    require(before['event']['status']=='Under Review' and before['assignment']['coordinator_id']==h.identities['assigned']['id'],'Fixture state/current actor changed; no reassignment retry')
    h.check_history(event,before['history'],['Submitted','Under Review'])
    status,oldread=h.request('GET',f'/event-requests/{event}/status-history',role='assigned')
    require(status==200 and oldread==before['history'],'Former actor pre-read unavailable')
    h.report['before']=before;h.report['old_pre_read']={'status':status,'body':oldread};h.save()
    status,assignment=h.request('POST',f'/event-requests/{event}/coordinator',role='manager',body={'coordinator_id':h.identities['replacement']['id']})
    h.report['assignment_response']={'status':status,'body':assignment};h.save()
    require(status==201,'Intended reassignment did not return201; no retry')
    after=h.snapshot(event)
    require(after['event']==before['event'] and after['history']==before['history'] and after['decisions']==before['decisions'],'Reassignment changed protected API state')
    require(after['assignment']==assignment and assignment['id']!=before['assignment']['id'] and assignment['coordinator_id']==h.identities['replacement']['id'] and assignment['assigned_by']==h.identities['manager']['id'],'Wrong intended assignment metadata')
    status,denied=h.request('GET',f'/event-requests/{event}/status-history',role='assigned')
    h.report['old_post_read']={'status':status,'body':denied};h.save()
    require(status==404 and denied=={'detail':{'code':'HISTORY_NOT_FOUND','message':'Status history is not accessible'}},'Former history scope not revoked')
    require(h.snapshot(event)==after,'Former refused read changed state')
    status,denied=h.request('POST',f'/event-requests/{event}/cancellation',role='assigned',body={})
    h.report['old_stale_action']={'method':'POST','path':'cancellation','status':status,'body':denied};h.save()
    require(status==403 and denied=={'detail':f'Only the Coordinator currently assigned to event request {event} can change its status'},'Former valid-source action not refused403 exactly')
    require(h.snapshot(event)==after,'Former refused mutation changed API state')
    status,newread=h.request('GET',f'/event-requests/{event}/status-history',role='replacement')
    h.report['new_read']={'status':status,'body':newread};h.save()
    require(status==200 and newread==before['history'],'Replacement cannot read complete unchanged evidence')
    require(h.snapshot(event)==after,'Replacement read changed state')
    h.report.update({'after':after,'result':'PASS','retained_current_coordinator':h.identities['replacement']['id']});h.save()
    print({'case':'AC5-X3','result':'PASS','event':event,'current_coordinator':h.identities['replacement']['id'],'report':str(h.report_path)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event-id', type=UUID, required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--auth-url', default='http://127.0.0.1:8001')
    parser.add_argument('--event-url', default='http://127.0.0.1:8003')
    parser.add_argument('--ui-url', default='http://127.0.0.1:3000')
    parser.add_argument('--allow-shared-test-write', action='store_true')
    args=parser.parse_args()
    args.mode='reassignment'
    h=None
    try:
        require(args.allow_shared_test_write,'Explicit shared test write opt-in required')
        h=Harness(args)
        verify_reassignment(h,str(args.event_id))
    except (AssertionError,KeyError,OSError,RuntimeError,TypeError,ValueError) as error:
        message=str(error) if isinstance(error,AssertionError) else type(error).__name__
        if h is not None:
            h.report.update({'result':'FAIL','failure':message});h.save()
        print({'case':'AC5-X3','result':'FAIL','failure':message})
        raise SystemExit(1)


if __name__=='__main__':
    main()
