﻿CREATE TABLE config_category
(
  id serial,
  name character varying NOT NULL,
  display_order int NOT NULL default 0,
  CONSTRAINT config_category_pkey PRIMARY KEY (id)
)