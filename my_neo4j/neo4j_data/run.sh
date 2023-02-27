docker rm -f rasa_neo4j
docker run  -d \
--name rasa_neo4j   \
-v $(pwd)/data:/var/lib/neo4j/data  \
-v $(pwd)/log:/var/lib/neo4j/logs  \
-v $(pwd)/conf:/var/lib/neo4j/conf  \
-v $(pwd)/import:/var/lib/neo4j/import \
--env=NEO4J_AUTH=none  \
--publish=7474:7474  \
--restart=always  \
--publish=7687:7687 \
neo4j:4.1