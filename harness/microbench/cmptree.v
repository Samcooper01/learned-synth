// Comparison datapath: reduce many words to their maximum. Structure =
// comparator + mux tree, mixed compare/select.
module cmptree #(parameter W = 16, parameter N = 24) (
    input  [W*N-1:0]  din,
    output [W-1:0]    dmax
);
    integer i;
    reg [W-1:0] m;
    always @* begin
        m = 0;
        for (i = 0; i < N; i = i + 1)
            if (din[i*W +: W] > m)
                m = din[i*W +: W];
    end
    assign dmax = m;
endmodule
