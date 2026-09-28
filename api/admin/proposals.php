<?php
declare(strict_types=1);
require_once __DIR__ . '/../../backend/bootstrap.php';
$user=sk_require_user();$db=sk_db();$method=$_SERVER['REQUEST_METHOD']??'GET';
$proposalsT=sk_table('event_change_proposals');$eventsT=sk_table('events');$datesT=sk_table('event_dates');$catsT=sk_table('event_categories');$locationsT=sk_table('event_locations');$sourcesT=sk_table('event_sources');$revisionsT=sk_table('event_revisions');
if($method==='GET'){
 $rows=$db->query("SELECT p.id,p.event_id,p.severity,p.proposed_json,p.detected_changes_json,p.created_at,e.title FROM {$proposalsT} p JOIN {$eventsT} e ON e.id=p.event_id WHERE p.status='pending' ORDER BY (p.severity='important') DESC,p.created_at DESC")->fetchAll();
 foreach($rows as &$r){$r['proposed']=json_decode($r['proposed_json'],true);$r['changes']=json_decode($r['detected_changes_json'],true);unset($r['proposed_json'],$r['detected_changes_json']);}
 sk_json(['proposals'=>$rows]);
}
if($method!=='POST')sk_json(['error'=>'method_not_allowed'],405);
$b=sk_body();$id=(int)($b['id']??0);$action=$b['action']??'';if(!$id||!in_array($action,['accept','reject'],true))sk_json(['error'=>'invalid_request'],400);
$q=$db->prepare("SELECT * FROM {$proposalsT} WHERE id=? AND status='pending'");$q->execute([$id]);$p=$q->fetch();if(!$p)sk_json(['error'=>'not_found'],404);
if($action==='reject'){$db->prepare("UPDATE {$proposalsT} SET status='rejected',resolved_at=NOW(),resolved_by=? WHERE id=?")->execute([$user['id'],$id]);sk_json(['ok'=>true]);}
$e=json_decode($p['proposed_json'],true);$eventId=(int)$p['event_id'];
$db->beginTransaction();try{
 $q=$db->prepare("UPDATE {$eventsT} SET title=?,description=?,city=?,place=?,region=?,country=?,route=?,organizer=?,time_start=?,time_end=?,all_day=?,status=?,review_status='human_reviewed',source_kind='manual' WHERE id=?");
 $q->execute([$e['title'],$e['description'],$e['city'],$e['place'],$e['region'],$e['country'],$e['route'],$e['organizer'],$e['time_start'],$e['time_end'],$e['all_day'],$e['status'],$eventId]);
 foreach([$datesT,$catsT,$locationsT,$sourcesT] as $t)$db->prepare("DELETE FROM {$t} WHERE event_id=?")->execute([$eventId]);
 $q=$db->prepare("INSERT INTO {$datesT}(event_id,starts_on,ends_on,starts_at,ends_at,sort_order) VALUES (?,?,?,?,?,?)");foreach($e['dates'] as $i=>$d)$q->execute([$eventId,$d['starts_on'],$d['ends_on'],$e['time_start'],$e['time_end'],$i]);
 $q=$db->prepare("INSERT INTO {$catsT}(event_id,category) VALUES (?,?)");foreach($e['categories'] as $c)$q->execute([$eventId,$c]);
 $q=$db->prepare("INSERT INTO {$locationsT}(event_id,label,sort_order) VALUES (?,?,?)");foreach($e['locations'] as $i=>$l)$q->execute([$eventId,$l,$i]);
 $q=$db->prepare("INSERT INTO {$sourcesT}(event_id,url,is_primary,last_seen_at) VALUES (?,?,?,NOW())");foreach($e['sources'] as $i=>$u)$q->execute([$eventId,$u,$i===0?1:0]);
 $snap=sk_event_snapshot($db,(string)$eventId);$db->prepare("INSERT INTO {$revisionsT}(event_id,actor_type,actor_user_id,action,snapshot_json,note) VALUES (?,\"user\",?,\"update\",?,?)")->execute([$eventId,$user['id'],json_encode($snap,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),'Přijat návrh změny z automatické synchronizace']);
 $db->prepare("UPDATE {$proposalsT} SET status='accepted',resolved_at=NOW(),resolved_by=? WHERE id=?")->execute([$user['id'],$id]);$db->commit();sk_json(['ok'=>true,'event'=>$snap]);
}catch(Throwable $ex){$db->rollBack();sk_json(['error'=>'server_error'],500);}
