// Sparse sequential feedback: a maximal-length LFSR. Structure = mostly flip-flop
// shift register with a tiny sparse XOR feedback, very low combinational density.
module lfsr #(parameter W = 64) (
    input              clk,
    input              rst,
    output reg [W-1:0] state
);
    wire fb = state[63] ^ state[62] ^ state[60] ^ state[59];
    always @(posedge clk)
        if (rst) state <= {W{1'b1}};
        else     state <= {state[W-2:0], fb};
endmodule
