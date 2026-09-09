module formal_top;
  (* gclk *) reg pclk;

  (* anyseq *) reg         prstn;
  (* anyseq *) reg         csb2nvdla_ready;
  (* anyseq *) reg  [31:0] nvdla2csb_data;
  (* anyseq *) reg         nvdla2csb_valid;
  (* anyseq *) reg  [31:0] paddr;
  (* anyseq *) reg         penable;
  (* anyseq *) reg         psel;
  (* anyseq *) reg  [31:0] pwdata;
  (* anyseq *) reg         pwrite;

  wire [15:0] csb2nvdla_addr;
  wire        csb2nvdla_nposted;
  wire        csb2nvdla_valid;
  wire [31:0] csb2nvdla_wdat;
  wire        csb2nvdla_write;
  wire [31:0] prdata;
  wire        pready;

  NV_NVDLA_apb2csb dut (
    .pclk(pclk),
    .prstn(prstn),
    .csb2nvdla_ready(csb2nvdla_ready),
    .nvdla2csb_data(nvdla2csb_data),
    .nvdla2csb_valid(nvdla2csb_valid),
    .paddr(paddr),
    .penable(penable),
    .psel(psel),
    .pwdata(pwdata),
    .pwrite(pwrite),
    .csb2nvdla_addr(csb2nvdla_addr),
    .csb2nvdla_nposted(csb2nvdla_nposted),
    .csb2nvdla_valid(csb2nvdla_valid),
    .csb2nvdla_wdat(csb2nvdla_wdat),
    .csb2nvdla_write(csb2nvdla_write),
    .prdata(prdata),
    .pready(pready)
  );

  wire apb_access = psel && penable;
  wire read_access = apb_access && !pwrite;
  wire write_access = apb_access && pwrite;
  wire read_request_accepted =
    read_access && csb2nvdla_valid && csb2nvdla_ready;

  reg f_past_valid = 1'b0;
  reg f_outstanding_read = 1'b0;

  initial assume(!prstn);

  // Environment assumptions. These constrain only top-level DUT inputs.
  always @(posedge pclk) begin
    f_past_valid <= 1'b1;

    if (!f_past_valid) begin
      assume(!prstn);
    end else begin
      assume(prstn);
    end

    if (!prstn) begin
      assume(!psel);
      assume(!penable);
      assume(!nvdla2csb_valid);
    end else begin
      // APB phase legality and stable control/data during wait states.
      assume(!penable || psel);
      if (apb_access) begin
        assume(
          $past(psel && !penable) ||
          $past(psel && penable && !pready)
        );
        assume(paddr[1:0] == 2'b00);
        assume(paddr[31:18] == 14'b0);
      end
      if ($past(psel && penable && !pready)) begin
        assume(psel && penable);
        assume($stable(paddr));
        assume($stable(pwrite));
        assume($stable(pwdata));
      end

      // Pilot CSB response model.
      if (nvdla2csb_valid) begin
        assume(f_outstanding_read);
      end
      if (read_request_accepted) begin
        assume(!nvdla2csb_valid);
      end
    end
  end

  // Environment bookkeeping is independent of the DUT's private state.
  always @(posedge pclk) begin
    if (!prstn) begin
      f_outstanding_read <= 1'b0;
    end else if (nvdla2csb_valid) begin
      f_outstanding_read <= 1'b0;
    end else if (read_request_accepted) begin
      f_outstanding_read <= 1'b1;
    end
  end

  // Safety assertions are deliberately separate from the cover monitor.
  always @(posedge pclk) begin
    if (f_past_valid && prstn) begin
      assert(csb2nvdla_addr == paddr[17:2]);
      assert(csb2nvdla_wdat == pwdata);
      assert(csb2nvdla_write == pwrite);
      assert(csb2nvdla_nposted == 1'b0);
      assert(prdata == nvdla2csb_data);

      if (write_access) begin
        assert(pready == csb2nvdla_ready);
      end
      if (read_access) begin
        assert(pready == nvdla2csb_valid);
      end
      if (read_request_accepted) begin
        assert(!f_outstanding_read);
      end
    end
  end

  localparam [2:0] TARGET_IDLE = 3'd0;
  localparam [2:0] TARGET_STALLED = 3'd1;
  localparam [2:0] TARGET_ACCEPTED = 3'd2;
  localparam [2:0] TARGET_WAITED = 3'd3;
  localparam [2:0] TARGET_HIT = 3'd4;

  reg [2:0] target_state = TARGET_IDLE;
  reg [31:0] accepted_response_data;

  // Shared semantic target: stalled read, acceptance, wait, one response,
  // completion with matching data. Adjacent events may share a cycle.
  always @(posedge pclk) begin
    if (!prstn) begin
      target_state <= TARGET_IDLE;
      accepted_response_data <= 32'b0;
    end else begin
      case (target_state)
        TARGET_IDLE:
          if (read_access && csb2nvdla_valid && !csb2nvdla_ready)
            target_state <= TARGET_STALLED;
        TARGET_STALLED:
          if (read_request_accepted)
            target_state <= TARGET_ACCEPTED;
        TARGET_ACCEPTED:
          if (read_access && !pready && !nvdla2csb_valid)
            target_state <= TARGET_WAITED;
        TARGET_WAITED:
          if (read_access && nvdla2csb_valid) begin
            accepted_response_data <= nvdla2csb_data;
            if (pready && prdata == nvdla2csb_data)
              target_state <= TARGET_HIT;
          end
        TARGET_HIT:
          target_state <= TARGET_HIT;
        default:
          target_state <= TARGET_IDLE;
      endcase
    end
  end

  always @(posedge pclk) begin
    cover(target_state == TARGET_HIT);
  end
endmodule
