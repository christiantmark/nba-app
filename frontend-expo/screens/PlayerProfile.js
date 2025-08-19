import React, { useState, useEffect } from "react";
import { View, Text, Image, StyleSheet, ActivityIndicator } from "react-native";

export default function PlayerProfile({ route }) {
  const { player } = route.params;

  const [playerNameMap, setPlayerNameMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [imageError, setImageError] = useState(false);

  const playerId = player.playerId || player.id || "2544";

  // Fetch the player map from your Flask endpoint
  useEffect(() => {
    fetch("https://lyvframe.com/nba/player_map?client_id=be3c14f8-c257-48f0-becd-0fa0c367f6aa")
      .then((res) => res.json())
      .then((data) => setPlayerNameMap(data))
      .catch((err) => console.error("Failed to fetch player map:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <ActivityIndicator size="large" color="black" style={{ flex: 1 }} />;
  }

  const fullName = playerNameMap[playerId] || player.name || "Unknown Player";

  return (
    <View style={styles.container}>
      <Image
        source={{
          uri: imageError
            ? "https://cdn-icons-png.flaticon.com/512/149/149071.png"
            : `https://cdn.nba.com/headshots/nba/latest/1040x760/${playerId}.png`,
        }}
        style={styles.headshot}
        resizeMode="contain"
        onError={() => setImageError(true)}
      />
      <Text style={styles.name}>{fullName}</Text>
      <Text style={styles.id}>ID: {playerId}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: "#000",
    alignItems: "center",
    justifyContent: "center",
  },
  headshot: {
    width: 200,
    height: 200,
    marginBottom: 20,
    borderRadius: 10,
    backgroundColor: "#222",
  },
  name: {
    fontSize: 24,
    fontWeight: "bold",
    color: "white",
  },
  id: {
    fontSize: 16,
    color: "gray",
  },
});
