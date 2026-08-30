// Mux fabric: every output independently selects any input. Structure = many
// parallel wide muxes, very high fanout on inputs.
module crossbar #(parameter W = 8, parameter N = 16, parameter SB = 4) (
    input  [W*N-1:0]   din,
    input  [N*SB-1:0]  sel,
    output [W*N-1:0]   dout
);
    genvar o;
    generate
        for (o = 0; o < N; o = o + 1) begin : outp
            assign dout[o*W +: W] = din[ sel[o*SB +: SB]*W +: W ];
        end
    endgenerate
endmodule
