import React from "react";
import Svg, { Path, Circle, Ellipse, G } from "react-native-svg";
import { View } from "react-native";
// Original vector illustration: scales cleanly from small phones to tablets.
export function Garden() {
  return (
    <View
      accessible={false}
      style={{ height: 155, overflow: "hidden", borderRadius: 24 }}
    >
      <Svg
        width="100%"
        height="100%"
        viewBox="0 0 620 190"
        preserveAspectRatio="xMidYMid slice"
      >
        <Path fill="#B8D5D0" d="M0 0H620V190H0Z" />
        <Circle cx="450" cy="45" r="28" fill="#FFF3B5" />
        <Path fill="#6A9A70" d="M0 120Q120 20 300 110T620 45V190H0Z" />
        <Path fill="#28674C" d="M0 110Q160 195 360 85T620 80V190H0Z" />
        <Path
          fill="#A5C865"
          d="M170 190Q240 155 380 130T620 115L620 129Q430 137 335 166L290 190Z"
        />
        {Array.from({ length: 38 }, (_, i) => {
          const x = (i * 97) % 630,
            y = 110 + ((i * 37) % 80);
          return (
            <G key={i}>
              <Path
                d={`M${x} ${y + 17}q-4 -9 0 -17`}
                stroke="#C6DA7D"
                strokeWidth="2"
              />
              <Ellipse cx={x - 4} cy={y + 8} rx="5" ry="2" fill="#99BC68" />
              {[0, 1, 2, 3, 4].map((p) => (
                <Circle
                  key={p}
                  cx={x + Math.cos(p * 1.256) * 4}
                  cy={y + Math.sin(p * 1.256) * 4}
                  r={3.8}
                  fill={["#FA8E47", "#ED92C5", "#DBE877", "#FCF1CD"][i % 4]}
                />
              ))}
              <Circle cx={x} cy={y} r="2" fill="#FAE67A" />
            </G>
          );
        })}
      </Svg>
    </View>
  );
}
