-- DUMMY DATA ONLY, FOR USE IN UNIT TESTS

SET FOREIGN_KEY_CHECKS=0;

DELETE FROM player_events;
DELETE FROM reported_user;
DELETE FROM moderation_report;
DELETE FROM teamkills;
DELETE FROM unique_id_users;
DELETE FROM uniqueid;
DELETE FROM global_rating;
DELETE FROM ladder1v1_rating;
DELETE FROM uniqueid_exempt;
DELETE FROM version_lobby;
DELETE FROM friends_and_foes;
DELETE FROM ladder_map;
DELETE FROM tutorial;
DELETE FROM map_version_review;
DELETE FROM map_version_reviews_summary;
DELETE FROM map_version;
DELETE FROM `map`;
DELETE FROM coop_map;
DELETE FROM mod_version_review;
DELETE FROM mod_version_reviews_summary;
DELETE FROM mod_version;
DELETE FROM `mod`;
DELETE FROM mod_stats;
DELETE FROM oauth_clients;
DELETE FROM updates_faf;
DELETE FROM updates_faf_files;
DELETE FROM avatars;
DELETE FROM avatars_list;
DELETE FROM ban;
DELETE FROM clan_membership;
DELETE FROM clan;
DELETE FROM game_player_stats;
DELETE FROM game_review;
DELETE FROM game_reviews_summary;
DELETE FROM game_stats;
DELETE FROM game_featuredMods;
DELETE FROM game_featuredMods_version;
DELETE FROM ladder_division_score;
DELETE FROM ladder_division;
DELETE FROM lobby_admin;
DELETE FROM name_history;
DELETE FROM user_group_assignment;
DELETE FROM login;
DELETE FROM email_domain_blacklist;
DELETE FROM leaderboard_rating_journal;
DELETE FROM leaderboard_rating;
DELETE FROM leaderboard;
DELETE FROM matchmaker_queue;
DELETE FROM matchmaker_queue_game;
DELETE FROM matchmaker_queue_map_pool;
DELETE FROM map_pool;
DELETE FROM map_pool_map_version;
DELETE FROM user_group;
DELETE FROM group_permission_assignment;

SET FOREIGN_KEY_CHECKS=1;

-- Login table
-- Most accounts get a creation time in the past so that they pass account
-- age check.
insert into login (id, login, email, password, steamid, create_time) values
  (1, 'test', 'test@example.com', SHA2('test_password', 256),    null, '2000-01-01 00:00:00'),
  (2, 'Dostya', 'dostya@arm.example.com', SHA2('vodka', 256), null, '2000-01-01 00:00:00'),
  (3, 'Rhiza', 'rhiza@gok.example.com', SHA2('puff_the_magic_dragon', 256), null, '2000-01-01 00:00:00'),
  (4, 'No_UID', 'uid@core.example.com', SHA2('his_pw', 256), null, '2000-01-01 00:00:00'),
  (5, 'postman', 'postman@postman.com', SHA2('postman', 256), null, '2000-01-01 00:00:00'),
  (7, 'test2', 'test2@example.com', SHA2('test2', 256), null, '2000-01-01 00:00:00'),
  (8, 'test3', 'test3@example.com', SHA2('test3', 256), null, '2000-01-01 00:00:00'),
  (9, 'test4', 'test4@example.com', SHA2('test3', 256), null, '2000-01-01 00:00:00'),
  (10,  'friends', 'friends@example.com', SHA2('friends', 256),  null, '2000-01-01 00:00:00'),
  (20,  'moderator', 'moderator@example.com', SHA2('moderator', 256), null, '2000-01-01 00:00:00'),
  (50,  'player_service1', 'ps1@example.com', SHA2('player_service1', 256), null, '2000-01-01 00:00:00'),
  (51,  'player_service2', 'ps2@example.com', SHA2('player_service2', 256), null,  '2000-01-01 00:00:00'),
  (52,  'player_service3', 'ps3@example.com', SHA2('player_service3', 256), null, '2000-01-01 00:00:00'),
  (100, 'ladder1', 'ladder1@example.com', SHA2('ladder1', 256), null, '2000-01-01 00:00:00'),
  (101, 'ladder2', 'ladder2@example.com', SHA2('ladder2', 256), null, '2000-01-01 00:00:00'),
  (102, 'ladder3', 'ladder3@example.com', SHA2('ladder3', 256), null, '2000-01-01 00:00:00'),
  (103, 'ladder4', 'ladder4@example.com', SHA2('ladder4', 256), null, '2000-01-01 00:00:00'),
  (104, 'ladder_ban', 'ladder_ban@example.com', SHA2('ladder_ban', 256), null, '2000-01-01 00:00:00'),
  (105, 'tmm1', 'tmm1@example.com', SHA2('tmm1', 256), null, '2000-01-01 00:00:00'),
  (106, 'tmm2', 'tmm2@example.com', SHA2('tmm2', 256), null, '2000-01-01 00:00:00'),
  (200, 'banme', 'banme@example.com', SHA2('banme', 256), null, '2000-01-01 00:00:00'),
  (201, 'ban_revoked', 'ban_revoked@example.com', SHA2('ban_revoked', 256), null, '2000-01-01 00:00:00'),
  (202, 'ban_expired', 'ban_expired@example.com', SHA2('ban_expired', 256), null, '2000-01-01 00:00:00'),
  (203, 'ban_long_time', 'ban_null_expiration@example.com', SHA2('ban_long_time', 256), null, '2000-01-01 00:00:00'),
  (204, 'ban_46_hour', 'ban_46_hour_expiration@example.com', SHA2('ban_46_hour', 256), null, '2000-01-01 00:00:00'),
  (300, 'steam_id', 'steam_id@example.com', SHA2('steam_id', 256), 34632, '2000-01-01 00:00:00')
;
insert into login (id, login, email, password) values (6, 'newbie', 'noob@example.com', SHA2('password', 256));

-- Name history
insert into name_history (id, change_time, user_id, previous_name) values
  (1, date_sub(now(), interval 12 month), 1, 'test_maniac'),
  (2, date_sub(now(), interval 1 month), 2, 'YoungDostya');

insert into user_group (id, technical_name, public, name_key) values
  (1, 'faf_server_administrators', true, 'admins'),
  (2, 'faf_moderators_global', true, 'mods');

-- Permissions
insert into group_permission_assignment (id, group_id, permission_id) values
  (1, (SELECT id from user_group WHERE technical_name = 'faf_server_administrators'), (SELECT id from group_permission WHERE technical_name = 'ADMIN_BROADCAST_MESSAGE')),
  (2, (SELECT id from user_group WHERE technical_name = 'faf_server_administrators'), (SELECT id from group_permission WHERE technical_name = 'ADMIN_KICK_SERVER')),
  (3, (SELECT id from user_group WHERE technical_name = 'faf_moderators_global'), (SELECT id from group_permission WHERE technical_name = 'ADMIN_KICK_SERVER'));

insert into lobby_admin (user_id, `group`) values (1, 2);
insert into user_group_assignment(user_id, group_id) values (1, (SELECT id from user_group WHERE technical_name = 'faf_server_administrators'));
insert into user_group_assignment(user_id, group_id) values (2, (SELECT id from user_group WHERE technical_name = 'faf_moderators_global'));
insert into user_group_assignment(user_id, group_id) values (20, (SELECT id from user_group WHERE technical_name = 'faf_moderators_global'));

INSERT INTO leaderboard (id,technical_name,name_key,description_key,create_time,update_time,initializer_id) VALUES
	 (1,'global','leaderboard.global.name','leaderboard.global.desc','2020-11-07 00:15:06','2020-11-07 00:15:06',NULL),
	 (2,'ladder1v1','leaderboard.ladder1v1_tacc.name','leaderboard.ladder1v1_tacc.desc','2020-11-07 00:15:06','2021-05-14 09:25:40',NULL),
	 (3,'ladder1v1_tavmod','leaderboard.ladder1v1_tavmod.name','leaderboard.ladder1v1_tavmod.desc','2021-05-14 09:25:41','2021-05-14 09:25:41',NULL);


insert into leaderboard_rating (login_id, mean, deviation, total_games, leaderboard_id) values
  (1, 2000, 125, 5, 1),
  (1, 2000, 125, 5, 2),
  (2, 1500, 75, 2, 1),
  (2, 1500, 75, 2, 2),
  (3, 1650, 62.52, 2, 1),
  (3, 1650, 62.52, 2, 2),
  (50,  1200, 250, 42, 1),
  (50,  1300, 400, 12, 2),
  (100, 1500, 500, 0, 1),
  (100, 1500, 500, 0, 2),
  (101, 1500, 500, 0, 1),
  (101, 1500, 500, 0, 2),
  (102, 1500, 500, 0, 1),
  (102, 1500, 500, 0, 2),
  (105, 1400, 150, 20, 3),
  (106, 1500, 75, 20, 3)
;

-- UniqueID_exempt
insert into uniqueid_exempt (user_id, reason) values (1, 'Because test');

-- UID Samples
INSERT INTO `uniqueid` (`hash`, `uuid`, `mem_SerialNumber`, `deviceID`, `manufacturer`, `name`, `processorId`, `SMBIOSBIOSVersion`, `serialNumber`, `volumeSerialNumber`)
VALUES ('some_id', '-', '-', '-', '-', '-', '-', '-', '-', '-'),
       ('another_id', '-', '-', '-', '-', '-', '-', '-', '-', '-');

-- Banned UIDs
insert into unique_id_users (user_id, uniqueid_hash) values (1, 'some_id');
insert into unique_id_users (user_id, uniqueid_hash) values (2, 'another_id');
insert into unique_id_users (user_id, uniqueid_hash) values (3, 'some_id');

-- Sample maps
insert into map (id, display_name, map_type, battle_type, author) values
  (1, 'SCMP_001', 'FFA', 'skirmish', 1),
  (2, 'SCMP_002', 'FFA', 'skirmish', 1),
  (3, 'SCMP_003', 'FFA', 'skirmish', 1),
  (4, 'SCMP_004', 'FFA', 'skirmish', 1),
  (5, 'SCMP_005', 'FFA', 'skirmish', 1),
  (6, 'SCMP_006', 'FFA', 'skirmish', 2),
  (7, 'SCMP_007', 'FFA', 'skirmish', 2),
  (8, 'SCMP_008', 'FFA', 'skirmish', 2),
  (9, 'SCMP_009', 'FFA', 'skirmish', 2),
  (10, 'SCMP_010', 'FFA', 'skirmish', 3),
  (11, 'SCMP_011', 'FFA', 'skirmish', 3),
  (12, 'SCMP_012', 'FFA', 'skirmish', 3),
  (13, 'SCMP_013', 'FFA', 'skirmish', 3),
  (14, 'SCMP_014', 'FFA', 'skirmish', 3),
  (15, 'SCMP_015', 'FFA', 'skirmish', 3);

insert into map_version (id, description, max_players, width, height, version, filename, hidden, ranked, map_id) values
  (1, 'SCMP 001', 8, 1024, 1024, 1, 'maps.ufo/scmp_001/12345678', 0, 1, 1),
  (2, 'SCMP 002', 8, 1024, 1024, 1, 'maps.ufo/scmp_002/abcdef0', 0, 1, 2),
  (3, 'SCMP 003', 8, 1024, 1024, 1, 'maps.ufo/scmp_003/1234abcd', 0, 1, 3),
  (4, 'SCMP 004', 8, 1024, 1024, 1, 'maps.ufo/scmp_004/abcd1234', 0, 1, 4),
  (5, 'SCMP 005', 8, 2048, 2048, 1, 'maps.ufo/scmp_005/1a2b3c4d', 0, 1, 5),
  (6, 'SCMP 006', 8, 1024, 1024, 1, 'maps.ufo/scmp_006/43214321', 0, 1, 6),
  (7, 'SCMP 007', 8, 512, 512, 1, 'maps.ufo/scmp_007/aaaaaaaa', 0, 1, 7),
  (8, 'SCMP 008', 8, 1024, 1024, 1, 'maps.ufo/scmp_008/bbbbbbbb', 0, 1, 8),
  (9, 'SCMP 009', 8, 1024, 1024, 1, 'maps.ufo/scmp_009/cccccccc', 0, 1, 9),
  (10, 'SCMP 010', 8, 1024, 1024, 1, 'maps.ufo/scmp_010/dddddddd', 0, 1, 10),
  (11, 'SCMP 011', 8, 2048, 2048, 1, 'maps.ufo/scmp_011/eeeeeeee', 0, 1, 11),
  (12, 'SCMP 012', 8, 256, 256, 1, 'maps.ufo/scmp_012/ffffffff', 0, 1, 12),
  (13, 'SCMP 013', 8, 256, 256, 1, 'maps.ufo/scmp_013/11111111', 0, 1, 13),
  (14, 'SCMP 014', 8, 1024, 1024, 1, 'maps.ufo/scmp_014/22222222', 0, 1, 14),
  (15, 'SCMP 015', 8, 512, 512, 1, 'maps.ufo/scmp_015/33333333', 0, 1, 15),
  (16, 'SCMP 015', 8, 512, 512, 2, 'maps.v0002.ufo/scmp_015/44444444', 0, 1, 15),
  (17, 'SCMP 015', 8, 512, 512, 3, 'maps.v0003.ufo/scmp_015/55555555', 0, 1, 15);

insert into ladder_map (id, idmap) values
  (1,1),
  (2,2);

INSERT INTO `coop_map` (`type`, `name`, `description`, `version`, `filename`) VALUES
  (1, 'GoK Campaign map', 'A map from the GoK campaign', 0, 'maps/scmp_coop_124.v0000.zip'),
  (2, 'Arm Campaign map', 'A map from the Arm campaign', 1, 'maps/scmp_coop_125.v0001.zip'),
  (3, 'CORE Campaign map',   'A map from the CORE campaign', 99, 'maps/scmp_coop_126.v0099.zip'),
  (100, 'Corrupted Map', 'This is corrupted and you should never see it', 0, '$invalid &string*');

INSERT INTO game_featuredMods (id,gamemod,description,name,publish,`order`,git_url,git_branch,file_extension,allow_override,deployment_webhook,install_package) VALUES
	 (1,'tacc','Total Annihilation: Core Contingency','Core Contingency',1,1,'https://git.taforever.com/ta-forever/featured_mods.git','tacc','tad',0,NULL,'{"url": "https://www.tauniverse.com/forum/attachment.php?attachmentid=37173&d=1623362752"}'),
	 (2,'ladder1v1','Total Annihilation: Core Contingency (Ladder 1v1)','ladder1v1',0,0,'https://git.taforever.com/ta-forever/featured_mods.git','tacc','tad',1,NULL,NULL),
	 (3,'taesc','Total Annihilation: Escalation','Escalation',1,3,'https://git.taforever.com/ta-forever/featured_mods.git','taesc','tae',0,NULL,'{"url": "http://taesc.tauniverse.com/downloads/TAESC_GOLD_9_9_1.rar;http://taesc.tauniverse.com/downloads/TAESC_FIX_9_9_2.rar", "folders": [{"regex": "Step_2[^/]*/(.*)"}, {"regex": "Step_3.*/Windows 8 or 10/(.*)", "platforms": ["win8", "win10"]}, {"regex": "Step_3.*/Linux or Mac/(.*)", "platforms": ["linux", "mac"]}, {"regex": "(eplayx.dll)"}]}'),
	 (4,'tazero','Total Annihilation: Zero','Zero',1,5,'https://git.taforever.com/ta-forever/featured_mods.git','tazero','tad',0,NULL,'{"url": "http://zero.tauniverse.com/downloads/TA_Zero_Base.zip;http://zero.tauniverse.com/downloads/TA_Zero_Alpha_4d.zip", "folders": [{"regex": "TA Zero/(.*)"}, {"regex": "([^/]+)"}, {"regex": "TA Zero Alpha 4d Fixes/Fix 10/(.*)", "platforms": ["win8", "win10"]}]}'),
	 (5,'tamayhem','Total Annihilation: Mayhem','Mayhem',1,6,'https://git.taforever.com/ta-forever/featured_mods.git','tamayhem','tad',0,NULL,'{"url": "https://mayhem.tauniverse.com/totalm/TotalM824e.zip"}'),
	 (6,'tavmod','Total Annihilation: ProTA','ProTA',1,2,'https://git.taforever.com/ta-forever/featured_mods.git','tavmod','pro',0,NULL,'{"url": "https://prota.tauniverse.com/ProTA4.4.zip"}'),
	 (7,'tatw','Total Annihilation: Twilight','Twilight',1,4,'https://git.taforever.com/ta-forever/featured_mods.git','tatw','tad',0,NULL,'{"url": "https://www.tauniverse.com/forum/attachment.php?attachmentid=37173&d=1623362752;https://content.taforever.com/featured_mod_dropins/TAT-v2.0-Beta-56.zip"}'),
	 (8,'tatalon','Total Annihilation: Talon','Talon',0,7,'https://git.taforever.com/ta-forever/featured_mods.git','','tad',NULL,NULL,NULL),
	 (9,'taexcess','Total Annilathion: Excess','Excess',0,8,'https://git.taforever.com/ta-forever/featured_mods.git','','tad',NULL,NULL,NULL);

INSERT INTO game_featuredMods_version (game_featuredMods_id,version,ta_hash,confirmed,observation_count,comment,git_branch,display_name) VALUES
	 (6,'4.3','4.3',1,0,NULL,NULL,NULL),
	 (6,'4.3','022871225a7fd5e3b97bda2ad73899a9',1,698,NULL,'tavmod-4.3','4.3'),
	 (3,'9.86','9.86',1,0,NULL,NULL,NULL),
	 (3,'9.86','e882ee9fc9d2e361612aa8e4cf53a52b',1,207,NULL,'taesc-9.86','9.8.6'),
	 (6,'4.3','1ef1cea8598dccf9fa80c7c2f94c1c05',0,9,NULL,NULL,NULL),
	 (1,'3.1','881cddda192f17f5563c5650982841d1',0,90,'CC+flea+scarab+hhog+immo+fark+necro','tacc-3.9.02','3.9.02'),
	 (1,'3.1','ff6266aad4e16877d1467b66034eae8c',0,5,'CC+flea+scarab+hhog+immo+fark+necro+QFluxor','tacc-3.9.02','3.9.02'),
	 (7,'3.1','9d083dd8d506b41ca819c2987b685af8',0,39,NULL,'tatw-2.0b52','2.0 beta 52'),
	 (5,'8.1','50ec609145bb9e3fed2aa0c766f72aa3',0,56,NULL,'tamayhem-8.1.5','8.1.5'),
	 (6,'4.3','7b644aa331e346c28ca084bdc6f5e174',0,1,NULL,NULL,NULL);
INSERT INTO game_featuredMods_version (game_featuredMods_id,version,ta_hash,confirmed,observation_count,comment,git_branch,display_name) VALUES
	 (3,'9.8','64ef1153a1019ba6b6874296be0c9e08',0,1,NULL,NULL,NULL),
	 (7,'3.1','3f2ea84d6971ed5240fa98e484f5b1b9',0,1,NULL,NULL,NULL),
	 (3,'9.86','35d28638a7e8a042d56ad3d5c7f92045',0,3,NULL,NULL,NULL),
	 (6,'4.3','d41d8cd98f00b204e9800998ecf8427e',0,1,NULL,NULL,NULL),
	 (6,'4.3','db2b00111041f67363c06ddd32e43215',0,1,NULL,NULL,NULL),
	 (6,'4.3','3216809dc7ab6abcb13524e39b23bb6d',0,1,NULL,NULL,NULL),
	 (6,'4.3','ad2dff4285aef45bce3d2ee50efcc640',0,1,NULL,NULL,NULL),
	 (6,'4.3','c543bd0ed11742bc9bf34f7c88b968c5',0,58,NULL,NULL,NULL),
	 (6,'4.3','0545fffddce117518af6825cab092735',0,2,NULL,NULL,NULL),
	 (6,'9.86','e882ee9fc9d2e361612aa8e4cf53a52b',0,2,NULL,NULL,NULL);
INSERT INTO game_featuredMods_version (game_featuredMods_id,version,ta_hash,confirmed,observation_count,comment,git_branch,display_name) VALUES
	 (1,'9.86','e882ee9fc9d2e361612aa8e4cf53a52b',0,9,NULL,NULL,NULL),
	 (3,'9.86','2d8ff3cade65006f1c68016e4e3ea44d',0,2,NULL,NULL,NULL),
	 (3,'9.9','e125c7fa8fc192f6a41cdfef0cf9d5f6',1,81,NULL,'taesc-9.90','9.9.0'),
	 (3,'9.7','ffa6fbaa849b6ce76ee97702fabced09',0,1,NULL,NULL,NULL),
	 (1,'9.7','f702ac89d703e842f7eaf41cae762b28',0,2,NULL,NULL,NULL),
	 (3,'9.7','f702ac89d703e842f7eaf41cae762b28',0,3,NULL,NULL,NULL),
	 (6,'4.3','3705e637b0e22a16b90a63eaeb454456',0,1,NULL,NULL,NULL),
	 (3,'9.9','327a647e55ed76ed49446e4878663d0b',0,2,NULL,NULL,NULL),
	 (1,'3.1','20f788dd66e4d90a8ba78915c5ba690d',0,3,NULL,NULL,NULL),
	 (1,'9.9','e125c7fa8fc192f6a41cdfef0cf9d5f6',0,9,NULL,NULL,NULL);
INSERT INTO game_featuredMods_version (game_featuredMods_id,version,ta_hash,confirmed,observation_count,comment,git_branch,display_name) VALUES
	 (3,'3.1','881cddda192f17f5563c5650982841d1',0,1,NULL,NULL,NULL),
	 (1,'3.1','9d083dd8d506b41ca819c2987b685af8',0,1,NULL,NULL,NULL),
	 (3,'9.9','9.9',1,0,NULL,NULL,NULL),
	 (3,'9.85','3894742b09c27e7b207a1890da45af37',0,1,NULL,NULL,NULL),
	 (6,'4.4','cdacdbed29ad1081f088a4cc0f537394',0,5,NULL,NULL,NULL);
 
insert into game_stats (id, startTime, gameName, gameType, gameMod, host, mapId, validity) values
  (1, NOW(), 'Test game', '0', 6, 1, 1, 0),
  (41935, NOW(), 'MapRepetition', '0', 6, 1, NULL, 0),
  (41936, NOW() + interval 1 minute, 'MapRepetition', '0', 6, 1, 1, 0),
  (41937, NOW() + interval 2 minute, 'MapRepetition', '0', 6, 1, 2, 0),
  (41938, NOW() + interval 3 minute, 'MapRepetition', '0', 6, 1, 3, 0),
  (41939, NOW() + interval 4 minute, 'MapRepetition', '0', 6, 1, 4, 0),
  (41940, NOW() + interval 5 minute, 'MapRepetition', '0', 6, 1, 5, 0),
  (41941, NOW() + interval 6 minute, 'MapRepetition', '0', 6, 1, 6, 0),
  (41942, NOW(), 'OldRatingNull',  '0', 6, 1, NULL, 0),
  (41943, NOW(), 'OldRatingLose', '0', 6, 1, NULL, 0),
  (41944, NOW(), 'OldRatingWin', '0', 6, 1, NULL, 0),
  (41945, NOW() + interval 7 minute, 'MapRepetition', '0', 6, 2, 6, 0),
  (41946, NOW() + interval 8 minute, 'MapRepetition', '0', 6, 2, 5, 0),
  (41947, NOW() + interval 9 minute, 'MapRepetition', '0', 6, 2, 4, 0),
  (41948, NOW() + interval 10 minute, 'MapRepetition', '0', 6, 2, 3, 0),
  (41949, NOW() + interval 1 minute, 'MapRepetition', '0', 6, 1, 7, 0),
  (41950, NOW() + interval 2 minute, 'MapRepetition', '0', 6, 1, 8, 0),
  (41951, NOW() + interval 3 minute, 'MapRepetition', '0', 6, 1, 9, 0),
  (41952, NOW() + interval 4 minute, 'MapRepetition', '0', 6, 1, 7, 0),
  (41953, NOW() + interval 1 minute, 'MapRepetition', '0', 6, 2, 5, 0),
  (41954, NOW() + interval 2 minute, 'MapRepetition', '0', 6, 2, 6, 0),
  (41955, NOW() + interval 3 minute, 'MapRepetition', '0', 6, 2, 7, 0);

insert into game_player_stats (gameId, playerId, AI, faction, color, team, place, mean, deviation, scoreTime) values
  (1, 1, 0, 0, 0, 2, 0, 1500, 500, NOW()),
  (1, 2, 0, 0, 0, 2, 0, 1500, 500, NOW()),
  (41935, 1, 0, 0, 0, 2, 0, 1500, 500, NOW()),
  (41936, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 1 minute),
  (41937, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 2 minute),
  (41938, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 3 minute),
  (41939, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 4 minute),
  (41940, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 5 minute),
  (41941, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 6 minute),
  (41945, 2, 0, 0, 0, 1, 0, 1500, 500, NOW() + interval 7 minute),
  (41946, 2, 0, 0, 0, 1, 0, 1500, 500, NOW() + interval 8 minute),
  (41947, 2, 0, 0, 0, 1, 0, 1500, 500, NOW() + interval 9 minute),
  (41948, 2, 0, 0, 0, 1, 0, 1500, 500, NOW() + interval 10 minute),
  (41949, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 1 minute),
  (41950, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 2 minute),
  (41951, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 3 minute),
  (41952, 1, 0, 0, 0, 2, 0, 1500, 500, NOW() + interval 4 minute),
  (41953, 2, 0, 0, 0, 1, 0, 1500, 500, NOW() + interval 1 minute),
  (41954, 2, 0, 0, 0, 1, 0, 1500, 500, NOW() + interval 2 minute),
  (41955, 2, 0, 0, 0, 1, 0, 1500, 500, NOW() + interval 3 minute);

insert into game_player_stats (gameId, playerId, AI, faction, color, team, place, mean, deviation, scoreTime, after_mean) values
  (41942, 51, 0, 0, 0, 2, 0, 1500, 500, NOW(), NULL),
  (41943, 51, 0, 0, 0, 2, 0, 1500, 500, NOW(), 1400),
  (41944, 51, 0, 0, 0, 2, 0, 1500, 500, NOW(), 1600);

INSERT INTO matchmaker_queue (id,technical_name,featured_mod_id,leaderboard_id,name_key,create_time,update_time,team_size,enabled) VALUES
	 (1,'ladder1v1_tacc',1,2,'matchmaker.ladder1v1','2021-05-14 09:25:41','2021-05-14 09:25:41',1,1),
	 (2,'ladder1v1_tavmod',6,3,'matchmaker.ladder1v1_tavmod','2021-05-14 09:25:41','2021-05-14 09:25:41',1,1);

insert into matchmaker_queue_game (matchmaker_queue_id, game_stats_id) values
  (1, 1),
  (1, 41935),
  (1, 41936),
  (1, 41937),
  (1, 41938),
  (1, 41939),
  (1, 41940),
  (1, 41941),
  (1, 41942),
  (1, 41943),
  (1, 41944),
  (1, 41945),
  (1, 41946),
  (1, 41947),
  (1, 41948),
  (2, 41949),
  (2, 41950),
  (2, 41951),
  (2, 41952),
  (2, 41953),
  (2, 41954),
  (2, 41955);

INSERT INTO map_pool (id,name,create_time,update_time) VALUES
	 (1,'tacc 1v1','2020-11-07 00:15:08','2021-05-14 09:25:42'),
	 (2,'tavmod 1v1','2021-05-14 09:25:43','2021-05-14 09:25:43');

INSERT INTO map_pool_map_version (map_pool_id,map_version_id,weight,map_params,create_time,update_time) VALUES
	 (1,1,1,'null','2021-05-14 10:58:29','2021-05-14 10:58:29'),
	 (1,2,1,'null','2021-05-14 10:58:30','2021-05-14 10:58:30'),
	 (1,3,1,'null','2021-05-14 10:58:30','2021-05-14 10:58:30'),
	 (1,4,1,'null','2021-05-14 10:58:30','2021-05-14 10:58:30'),
	 (1,5,1,'null','2021-05-14 10:58:30','2021-05-14 10:58:30'),
	 (1,6,1,'null','2021-05-14 10:58:31','2021-05-14 10:58:31'),
	 (1,7,1,'null','2021-05-14 10:58:31','2021-05-14 10:58:31'),
	 (1,8,1,'null','2021-05-14 10:58:31','2021-05-14 10:58:31'),
	 (1,9,1,'null','2021-05-14 10:58:32','2021-05-14 10:58:32'),
	 (1,10,1,'null','2021-05-14 10:58:32','2021-05-14 10:58:32');
INSERT INTO map_pool_map_version (map_pool_id,map_version_id,weight,map_params,create_time,update_time) VALUES
	 (1,11,1,'null','2021-05-14 10:58:32','2021-05-14 10:58:32'),
	 (2,12,1,'null','2022-01-21 21:55:47','2022-01-21 21:55:47'),
	 (2,13,1,'null','2022-01-21 21:55:47','2022-01-21 21:55:47'),
	 (2,14,1,'null','2022-01-21 21:55:47','2022-01-21 21:55:47'),
	 (2,15,1,'null','2022-01-21 21:55:47','2022-01-21 21:55:47'),
	 (2,16,1,'null','2022-01-21 21:55:47','2022-01-21 21:55:47'),
	 (2,17,1,'null','2022-01-21 21:55:47','2022-01-21 21:55:47'),
	 (2,1,1,'null','2022-01-21 21:55:47','2022-01-21 21:55:47'),
	 (2,2,1,'null','2022-01-21 21:55:47','2022-01-21 21:55:47'),
	 (2,3,1,'null','2022-01-21 21:55:47','2022-01-21 21:55:47');
INSERT INTO map_pool_map_version (map_pool_id,map_version_id,weight,map_params,create_time,update_time) VALUES
	 (2,4,1,'null','2022-01-21 21:55:48','2022-01-21 21:55:48'),
	 (2,5,1,'null','2022-01-21 21:55:48','2022-01-21 21:55:48'),
	 (2,6,1,'null','2022-01-21 21:55:48','2022-01-21 21:55:48'),
	 (2,7,1,'null','2022-01-21 21:55:48','2022-01-21 21:55:48'),
	 (2,8,1,'null','2022-01-21 21:55:48','2022-01-21 21:55:48');

INSERT INTO matchmaker_queue_map_pool (matchmaker_queue_id,map_pool_id,min_rating,max_rating,create_time,update_time) VALUES
	 (1,1,NULL,NULL,'2021-05-14 09:25:43','2021-05-14 09:25:43'),
	 (2,2,NULL,NULL,'2021-05-14 09:25:43','2021-05-14 09:25:43');

insert into friends_and_foes (user_id, subject_id, `status`) values
  (1, 3, 'FOE'),
  (2, 1, 'FRIEND'),
  (10, 1, 'FRIEND');

insert into `mod` (id, display_name, author) VALUES
  (1, 'test-mod', 'baz'),
  (2, 'test-mod2', 'baz'),
  (3, 'test-mod3', 'baz'),
  (100, 'Mod without icon', 'foo');

insert into mod_version (id, mod_id, uid, version, description, type, filename, icon) VALUES
  (1, 1, 'foo', 1, '', 'UI', 'foobar.zip', 'foobar.png'),
  (2, 1, 'bar', 2, '', 'SIM', 'foobar2.zip', 'foobar.png'),
  (3, 2, 'baz', 1, '', 'UI', 'foobar3.zip', 'foobar3.png'),
  (4, 3, 'EA040F8E-857A-4566-9879-0D37420A5B9D', 1, '', 'SIM', 'foobar4.zip', 'foobar4.png'),
  (5, 100, 'FFF', 1, 'The best version so far', 'UI', 'noicon.zip', null);

insert into mod_stats (mod_id, times_played, likers) VALUES
  (1, 0, ''),
  (2, 0, ''),
  (3, 1, '');

-- sample avatars
insert into avatars_list (id, filename, tooltip) values
  (1, 'qai2.png', 'QAI'),
  (2, 'CORE.png', 'CORE');

insert into avatars (idUser, idAvatar, selected) values
  (2, 1, 0),
  (2, 2, 1),
  (50, 2, 1),
  (51, 1, 0),
  (51, 2, 1),
  (52, 1, 1),
  (52, 2, 0);
insert into avatars (idUser, idAvatar, selected, expires_at) values (3, 1, 0, NOW());

-- sample bans
insert into ban(id, player_id, author_id, reason, level) values
  (1, 2, 1, 'Test permanent ban', 'GLOBAL'),
  (2, 4, 1, 'This test ban should be revoked', 'CHAT');
insert into ban(player_id, author_id, reason, level, expires_at) values
  (4, 1, 'This test ban should be expired', 'CHAT', NOW());
insert into ban (player_id, author_id, reason, level, expires_at, revoke_reason, revoke_author_id, revoke_time) values
  (4, 1, 'This test ban should be revoked', 'CHAT', DATE_ADD(NOW(), INTERVAL 1 YEAR), 'this was a test ban', 1, NOW());
insert into ban (player_id, author_id, reason, level, expires_at, revoke_time) values
  (201, 201, 'Test revoked ban', 'GLOBAL', NULL, now() - interval 1 day),
  (202, 202, 'Test expired ban', 'GLOBAL', now() - interval 1 day, NULL),
  (203, 203, 'Test permanent ban', 'GLOBAL', now() + interval 1000 year, NULL),
  (204, 204, 'Test ongoing ban with 46 hours left', 'GLOBAL', now() + interval 46 hour, NULL)
;

-- sample clans
insert into clan (id, name, tag, founder_id, leader_id, description) values
  (1, 'Alpha Clan', '123', 1, 1, 'Lorem ipsum dolor sit amet, consetetur sadipscing elitr'),
  (2, 'Beta Clan', '345', 4, 4, 'Sed diam nonumy eirmod tempor invidunt ut labore'),
  (3, 'Charlie Clan', '678', 2, 1, 'At vero eos et accusam et justo duo dolores et ea rebum');
insert into clan_membership (clan_id, player_id) values
  (1, 2),
  (1, 3),
  (2, 4),
  (3, 1),
  (1, 50);

-- sample oauth_client for Postman
insert into oauth_clients (id, name, client_secret, redirect_uris, default_redirect_uri, default_scope) VALUES
  ('3bc8282c-7730-11e5-8bcf-feff819cdc9f ', 'Downlord''s FAF Client', '{noop}6035bd78-7730-11e5-8bcf-feff819cdc9f', '', '', 'read_events read_achievements upload_map'),
  ('faf-website', 'faf-website', '{noop}banana', 'http://localhost:8020', 'http://localhost:8020', 'public_profile write_account_data create_user'),
  ('postman', 'postman', '{noop}postman', 'http://localhost https://www.getpostman.com/oauth2/callback', 'https://www.getpostman.com/oauth2/callback', 'read_events read_achievements upload_map upload_mod write_account_data');

insert into updates_faf (id, filename, path) values
  (1, 'ForgedAlliance.exe', 'bin'),
  (11, 'effects.nx2', 'gamedata'),
  (12, 'env.nx2', 'gamedata');

insert into updates_faf_files (id, fileId, version, name, md5, obselete) values
  (711, 1, 3658, 'ForgedAlliance.3658.exe', '2cd7784fb131ea4955e992cfee8ca9b8', 0),
  (745, 1, 3659, 'ForgedAlliance.3659.exe', 'ee2df6c3cb80dc8258428e8fa092bce1', 0),
  (723, 11, 3658, 'effects_0.3658.nxt', '3758baad77531dd5323c766433412e91', 0),
  (734, 11, 3659, 'effects_0.3659.nxt', '3758baad77531dd5323c766433412e91', 0),
  (680, 12, 3656, 'env_0.3656.nxt', '32a50729cb5155ec679771f38a151d29', 0);

insert into teamkills (teamkiller, victim, game_id, gametime) VALUES
  (1, 2, 1, 3600);

insert into game_review (id, text, user_id, score, game_id) VALUES
  (1, 'Awesome', 1, 5, 1),
  (2, 'Nice', 2, 3, 1),
  (3, 'Meh', 3, 2, 1);

insert into map_version_review (id, text, user_id, score, map_version_id) VALUES
  (1, 'Fine', 1, 3, 1),
  (2, 'Horrible', 2, 1, 1),
  (3, 'Boah!', 3, 5, 1);

insert into mod_version_review (id, text, user_id, score, mod_version_id) VALUES
  (1, 'Great!', 1, 5, 1),
  (2, 'Like it', 2, 4, 1),
  (3, 'Funny', 3, 4, 1);

INSERT INTO ladder_division VALUES
  (1, 'League 1 - Division A', 1, 10.0),
  (2, 'League 1 - Division B', 1, 30.0),
  (3, 'League 1 - Division C', 1, 50.0),
  (4, 'League 2 - Division D', 2, 20.0),
  (5, 'League 2 - Division E', 2, 60.0),
  (6, 'League 2 - Division F', 2, 100.0),
  (7, 'League 3 - Division D', 3, 100.0),
  (8, 'League 3 - Division E', 3, 200.0),
  (9, 'League 3 - Division F', 3, 9999.0);

INSERT INTO ladder_division_score (season, user_id, league, score, games) VALUES
  (1, 1, 1, 9.5, 4),
  (1, 2, 1, 49.5, 70),
  (1, 3, 2, 0.0, 39),
  (1, 4, 3, 10.0, 121);

INSERT INTO email_domain_blacklist VALUES ('spam.org');
