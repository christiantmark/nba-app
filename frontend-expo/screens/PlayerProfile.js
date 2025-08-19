import React, { useState } from 'react';
import { View, Text, StyleSheet, Image } from 'react-native';


const PlayerProfile = ({ route }) => {
  const { player } = route.params;
  console.log('🧍 Player:', player);


  const [imageError, setImageError] = useState(false);


  const playerId = player.playerId || player.id || '2544'; // fallback to LeBron
  const headshotUrl = imageError
    ? 'https://cdn-icons-png.flaticon.com/512/149/149071.png'
    : `https://cdn.nba.com/headshots/nba/latest/1040x760/${playerId}.png`;


  return (
    <View style={styles.container}>
      <Image
        source={{ uri: headshotUrl }}
        style={styles.headshot}
        resizeMode="contain"
        onError={() => {
          console.warn('❌ Failed to load headshot for:', playerId);
          setImageError(true);
        }}
      />
      <Text style={styles.name}>{player.name}</Text>
      <Text style={styles.id}>ID: {playerId}</Text>
    </View>
  );
};


const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: '#000',
    alignItems: 'center',
    justifyContent: 'center',
  },
  headshot: {
    width: 200,
    height: 200,
    marginBottom: 20,
    borderRadius: 10,
    backgroundColor: '#222',
  },
  name: {
    fontSize: 24,
    fontWeight: 'bold',
    color: 'white',
  },
  id: {
    fontSize: 16,
    color: 'gray',
  },
});


export default PlayerProfile;



