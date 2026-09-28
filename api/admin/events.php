<?php
declare(strict_types=1);
require_once __DIR__ . '/../../backend/bootstrap.php';
$user=sk_require_user();$method=$_SERVER['REQUEST_METHOD']??'GET';$db=sk_db();
$eventsT=sk_table('events');$datesT=sk_table('event_dates');$catsT=sk_table('event_categories');$sourcesT=sk_table('event_sources');$revisionsT=sk_table('event_revisions');$proposalsT=sk_table('event_change_proposals');

if($method==='POST'){
 $b=sk_body();$title=trim((string)($b['title']??''));if($title==='')sk_json(['error'=>'missing_title'],400);
 $db->beginTransaction();try{
  $q=$db->prepare("INSERT INTO {$eventsT}(title,description,city,place,region,country,route,organizer,time_start,time_end,all_day,public_url,status,review_status,source_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,\"human_reviewed\",\"manual\")");
  $q->execute([$title,$b['description']??null,$b['city']??null,$b['place']??null,$b['region']??null,$b['country']??null,$b['route']??null,$b['organizer']??null,$b['time_start']??null,$b['time_end']??null,!empty($b['all_day'])?1:0,$b['public_url']??null,in_array(($b['status']??''),['active','cancelled','hidden'],true)?$b['status']:'active']);
  $id=(int)$db->lastInsertId();
  $qd=$db->prepare("INSERT INTO {$datesT}(event_id,starts_on,ends_on,starts_at,ends_at,sort_order) VALUES (?,?,?,?,?,?)");foreach((array)($b['dates']??[]) as $i=>$d){if(empty($d['starts_on']))continue;$qd->execute([$id,$d['starts_on'],$d['ends_on']??$d['starts_on'],$d['starts_at']??null,$d['ends_at']??null,$i]);}
  $qc=$db->prepare("INSERT INTO {$catsT}(event_id,category) VALUES (?,?)");foreach(array_unique((array)($b['categories']??[])) as $c){if(in_array($c,['rail','bus','tram','trolleybus','metro','water','air','cableway','other'],true))$qc->execute([$id,$c]);}
  if(!empty($b['public_url']))$db->prepare("INSERT INTO {$sourcesT}(event_id,url,is_primary) VALUES (?,?,1)")->execute([$id,$b['public_url']]);
  $snap=sk_event_snapshot($db,(string)$id);$db->prepare("INSERT INTO {$revisionsT}(event_id,actor_type,actor_user_id,action,snapshot_json,note) VALUES (?,\"user\",?,\"create\",?,?)")->execute([$id,$user['id'],json_encode($snap,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),'Ručně vytvořená akce']);
  $db->commit();sk_json(['event'=>$snap],201);
 }catch(Throwable $e){$db->rollBack();sk_json(['error'=>'server_error'],500);}
}

if($method!=='GET')sk_json(['error'=>'method_not_allowed'],405);
try{
 $q=trim((string)($_GET['q']??''));$where=[];$params=[];
 if($q!==''){$where[]='(CAST(e.id AS CHAR) LIKE ? OR e.title LIKE ? OR e.city LIKE ? OR e.place LIKE ? OR e.region LIKE ?)';$like='%'.$q.'%';array_push($params,$like,$like,$like,$like,$like);}
 $sql="SELECT e.id FROM {$eventsT} e".($where?' WHERE '.implode(' AND ',$where):'')." ORDER BY (SELECT MIN(d.starts_on) FROM {$datesT} d WHERE d.event_id=e.id) DESC,e.updated_at DESC LIMIT 1000";
 $stmt=$db->prepare($sql);$stmt->execute($params);$events=[];foreach($stmt->fetchAll() as $row)$events[]=sk_event_snapshot($db,(string)$row['id']);
 $pending=(int)$db->query("SELECT COUNT(*) FROM {$proposalsT} WHERE status='pending'")->fetchColumn();sk_json(['events'=>$events,'pending_proposals'=>$pending]);
}catch(Throwable $e){sk_json(['error'=>'server_error'],500);}
